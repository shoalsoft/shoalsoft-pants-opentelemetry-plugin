# Copyright (C) 2025 Shoal Software LLC. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

import datetime
import enum
import logging
import multiprocessing
import queue
import signal
import sys
import threading
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from shoalsoft.pants_opentelemetry_plugin.processor import (
    IncompleteWorkunit,
    Processor,
    ProcessorContext,
    Workunit,
)

logger = logging.getLogger(__name__)


class MessageType(enum.Enum):
    INITIALIZE = "initialize"
    START_WORKUNIT = "start_workunit"
    COMPLETE_WORKUNIT = "complete_workunit"
    FINISH = "finish"
    SHUTDOWN = "shutdown"


@dataclass
class ProcessorMessage:
    type: MessageType
    data: Any = None


@dataclass
class InitializeData:
    processor_factory_data: Any


@dataclass
class StartWorkunitData:
    workunit: IncompleteWorkunit
    context_metrics: Mapping[str, int]


@dataclass
class CompleteWorkunitData:
    workunit: Workunit
    context_metrics: Mapping[str, int]


@dataclass
class FinishData:
    timeout: datetime.timedelta | None
    context_metrics: Mapping[str, int]


class _SerializableContext(ProcessorContext):
    def __init__(self, metrics: Mapping[str, int]) -> None:
        self._metrics = dict(metrics)

    def get_metrics(self) -> Mapping[str, int]:
        return self._metrics


def _subprocess_worker(
    request_queue: multiprocessing.Queue[ProcessorMessage],
    response_queue: multiprocessing.Queue[str],
    processor_factory: Callable[[Any], Processor],
) -> None:
    """Worker function that runs in a separate process to handle OpenTelemetry
    operations."""
    processor: Processor | None = None

    # Set up logging for subprocess
    logging.basicConfig(level=logging.DEBUG, format='[SUBPROCESS] %(levelname)s: %(message)s')
    logger.debug("_subprocess_worker: Entry point reached")

    try:
        # Ignore SIGINT in the subprocess - let the parent handle it
        logger.debug("_subprocess_worker: Setting up signal handler")
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        logger.debug("_subprocess_worker: Signal handler set up")

        logger.debug("_subprocess_worker: About to send 'started' message")
        response_queue.put("started")
        logger.debug("_subprocess_worker: 'started' message sent")

        logger.debug("_subprocess_worker: Entering main message loop")
        while True:
            try:
                logger.debug("_subprocess_worker: Waiting for message...")
                message = request_queue.get(timeout=1.0)
                logger.debug(f"_subprocess_worker: Received message: {message.type}")

                if message.type == MessageType.SHUTDOWN:
                    logger.debug("_subprocess_worker: Received shutdown signal")
                    break

                elif message.type == MessageType.INITIALIZE:
                    logger.debug("_subprocess_worker: Processing INITIALIZE message")
                    init_data: InitializeData = message.data

                    # Use the provided factory to create the processor
                    logger.debug("_subprocess_worker: Creating processor with factory")
                    processor = processor_factory(init_data.processor_factory_data)
                    logger.debug("_subprocess_worker: Processor created, initializing...")
                    processor.initialize()
                    logger.debug("_subprocess_worker: Processor initialized, sending confirmation")
                    response_queue.put("initialized")
                    logger.debug("_subprocess_worker: Initialization confirmation sent")

                elif message.type == MessageType.START_WORKUNIT:
                    if processor is None:
                        logger.error("Processor not initialized")
                        continue

                    start_data: StartWorkunitData = message.data
                    context = _SerializableContext(start_data.context_metrics)
                    processor.start_workunit(start_data.workunit, context=context)

                elif message.type == MessageType.COMPLETE_WORKUNIT:
                    if processor is None:
                        logger.error("Processor not initialized")
                        continue

                    complete_data: CompleteWorkunitData = message.data
                    context = _SerializableContext(complete_data.context_metrics)
                    processor.complete_workunit(complete_data.workunit, context=context)

                elif message.type == MessageType.FINISH:
                    if processor is None:
                        logger.error("Processor not initialized")
                        continue

                    finish_data: FinishData = message.data
                    context = _SerializableContext(finish_data.context_metrics)
                    processor.finish(timeout=finish_data.timeout, context=context)
                    response_queue.put("finished")

            except queue.Empty:
                logger.debug("_subprocess_worker: Queue timeout, continuing...")
                continue
            except Exception as e:
                logger.exception(f"_subprocess_worker: Error in message loop: {e}")
                response_queue.put(f"error: {e}")

    except Exception as e:
        logger.exception(f"_subprocess_worker: Fatal error in subprocess worker: {e}")
        try:
            response_queue.put(f"fatal_error: {e}")
        except:
            pass  # Queue might be broken
    finally:
        logger.debug("_subprocess_worker: Exiting subprocess worker")


class _DummyStdio:
    def __init__(self, fd):
        self._fd = fd

    def close(self):
        pass

    def __getattr__(self, name):
        if name == "close":
            return self.close
        else:
            return getattr(self._fd, name)


class MultiprocessingProcessor(Processor):
    """A processor that offloads OpenTelemetry operations to a separate process
    to avoid gRPC threading/fork issues."""

    def __init__(
        self,
        processor_factory: Callable[[Any], Processor],
        processor_factory_data: Any,
    ) -> None:
        self._processor_factory = processor_factory
        self._processor_factory_data = processor_factory_data

        # Communication with subprocess
        self._request_queue: multiprocessing.Queue[ProcessorMessage] = multiprocessing.Queue()
        self._response_queue: multiprocessing.Queue[str] = multiprocessing.Queue()
        self._subprocess: multiprocessing.Process | None = None
        self._shutdown_event = threading.Event()
        self._initialized = False

    def initialize(self) -> None:
        """Start the subprocess and initialize the OpenTelemetry processor."""
        logger.debug("MultiprocessingProcessor.initialize: Starting OpenTelemetry subprocess")

        # Install dummy stdio handlers to work around Pants-installed ones.
        logger.debug("MultiprocessingProcessor.initialize: Saving original stdio")
        saved_stdin = sys.stdin
        saved_stdout = sys.stdout
        saved_stderr = sys.stderr
        try:
            logger.debug("MultiprocessingProcessor.initialize: Installing dummy stdio handlers")
            sys.stdin = _DummyStdio(sys.stdin)
            sys.stdout = _DummyStdio(sys.stdout)
            sys.stderr = _DummyStdio(sys.stderr)

            # Start the subprocess
            logger.debug("MultiprocessingProcessor.initialize: Configuring multiprocessing logging")
            multiprocessing.log_to_stderr(logging.DEBUG)
            
            logger.debug("MultiprocessingProcessor.initialize: Creating subprocess")
            self._subprocess = multiprocessing.Process(
                target=_subprocess_worker,
                args=(self._request_queue, self._response_queue, self._processor_factory),
            )
            logger.debug("MultiprocessingProcessor.initialize: Starting subprocess")
            self._subprocess.start()
            logger.debug(f"MultiprocessingProcessor.initialize: Subprocess started with PID {self._subprocess.pid}")
        finally:
            logger.debug("MultiprocessingProcessor.initialize: Restoring original stdio")
            sys.stdin = saved_stdin
            sys.stdout = saved_stdout
            sys.stderr = saved_stderr

        # Wait for subprocess to start
        logger.debug("MultiprocessingProcessor.initialize: Waiting for subprocess startup confirmation")
        try:
            response = self._response_queue.get(timeout=10.0)
            logger.debug(f"MultiprocessingProcessor.initialize: Received startup response: {response}")
            if response != "started":
                raise RuntimeError(f"Subprocess failed to start: {response}")
        except queue.Empty:
            logger.error("MultiprocessingProcessor.initialize: Subprocess startup timeout")
            if self._subprocess:
                logger.error(f"MultiprocessingProcessor.initialize: Subprocess is_alive: {self._subprocess.is_alive()}")
                logger.error(f"MultiprocessingProcessor.initialize: Subprocess exitcode: {self._subprocess.exitcode}")
            raise RuntimeError("Subprocess failed to start within timeout")

        # Send initialization message
        logger.debug("MultiprocessingProcessor.initialize: Sending initialization message")
        init_data = InitializeData(
            processor_factory_data=self._processor_factory_data,
        )

        self._send_message(MessageType.INITIALIZE, init_data)

        # Wait for initialization confirmation
        logger.debug("MultiprocessingProcessor.initialize: Waiting for initialization confirmation")
        try:
            response = self._response_queue.get(timeout=30.0)
            logger.debug(f"MultiprocessingProcessor.initialize: Received initialization response: {response}")
            if response != "initialized":
                raise RuntimeError(f"Subprocess initialization failed: {response}")
        except queue.Empty:
            logger.error("MultiprocessingProcessor.initialize: Subprocess initialization timeout")
            if self._subprocess:
                logger.error(f"MultiprocessingProcessor.initialize: Subprocess is_alive: {self._subprocess.is_alive()}")
                logger.error(f"MultiprocessingProcessor.initialize: Subprocess exitcode: {self._subprocess.exitcode}")
            raise RuntimeError("Subprocess initialization timeout")

        logger.debug("MultiprocessingProcessor.initialize: OpenTelemetry subprocess initialized successfully")
        self._initialized = True

    def start_workunit(self, workunit: IncompleteWorkunit, *, context: ProcessorContext) -> None:
        """Send start workunit message to subprocess."""
        if self._shutdown_event.is_set() or not self._initialized:
            return

        try:
            data = StartWorkunitData(
                workunit=workunit,
                context_metrics=context.get_metrics(),
            )
            self._send_message(MessageType.START_WORKUNIT, data)
        except Exception as e:
            logger.warning(f"Failed to send start workunit: {e}")

    def complete_workunit(self, workunit: Workunit, *, context: ProcessorContext) -> None:
        """Send complete workunit message to subprocess."""
        if self._shutdown_event.is_set() or not self._initialized:
            return

        try:
            data = CompleteWorkunitData(
                workunit=workunit,
                context_metrics=context.get_metrics(),
            )
            self._send_message(MessageType.COMPLETE_WORKUNIT, data)
        except Exception as e:
            logger.warning(f"Failed to send complete workunit: {e}")

    def finish(
        self, timeout: datetime.timedelta | None = None, *, context: ProcessorContext
    ) -> None:
        """Send finish message to subprocess and wait for completion."""
        logger.debug("MultiprocessingProcessor.finish called")

        if self._shutdown_event.is_set():
            return

        self._shutdown_event.set()

        data = FinishData(
            timeout=timeout,
            context_metrics=context.get_metrics(),
        )
        self._send_message(MessageType.FINISH, data)

        # Wait for finish confirmation
        finish_timeout_seconds = timeout.total_seconds() if timeout else 30.0
        try:
            response = self._response_queue.get(timeout=finish_timeout_seconds)
            if response != "finished":
                logger.warning(f"Unexpected finish response: {response}")
        except queue.Empty:
            logger.warning("Subprocess finish timeout")

        # Shutdown subprocess
        self._send_message(MessageType.SHUTDOWN, None)

        if self._subprocess and self._subprocess.is_alive():
            self._subprocess.join(timeout=5.0)
            if self._subprocess.is_alive():
                logger.warning("Forcibly terminating subprocess")
                self._subprocess.terminate()
                self._subprocess.join(timeout=2.0)

        logger.debug("MultiprocessingProcessor.finish completed")

    def __del__(self) -> None:
        """Cleanup subprocess if not properly shutdown."""
        self._cleanup_subprocess()

    def _cleanup_subprocess(self) -> None:
        """Force cleanup of subprocess resources."""
        if self._subprocess and self._subprocess.is_alive():
            logger.warning("Forcibly cleaning up subprocess")
            try:
                self._subprocess.terminate()
                self._subprocess.join(timeout=2.0)
                if self._subprocess.is_alive():
                    self._subprocess.kill()
                    self._subprocess.join(timeout=1.0)
            except Exception as e:
                logger.exception(f"Error during subprocess cleanup: {e}")

    def _send_message(self, message_type: MessageType, data: Any) -> None:
        """Send a message to the subprocess."""
        logger.debug(f"MultiprocessingProcessor._send_message: Attempting to send {message_type}")
        
        if self._subprocess is None:
            logger.warning(f"MultiprocessingProcessor._send_message: Cannot send {message_type} - subprocess is None")
            return
            
        if not self._subprocess.is_alive():
            logger.warning(f"MultiprocessingProcessor._send_message: Cannot send {message_type} - subprocess not alive (exitcode: {self._subprocess.exitcode})")
            return

        try:
            message = ProcessorMessage(type=message_type, data=data)
            logger.debug(f"MultiprocessingProcessor._send_message: Putting message {message_type} in queue")
            self._request_queue.put(message, timeout=1.0)
            logger.debug(f"MultiprocessingProcessor._send_message: Message {message_type} sent successfully")
        except queue.Full:
            logger.warning(f"MultiprocessingProcessor._send_message: Failed to send {message_type} - queue full")
        except Exception as e:
            logger.exception(f"MultiprocessingProcessor._send_message: Error sending {message_type}: {e}")
