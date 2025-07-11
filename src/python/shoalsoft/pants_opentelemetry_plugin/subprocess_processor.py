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
import logging
import pickle
import struct
import subprocess
import sys
import threading
from pathlib import Path
from typing import Optional

from pants.util.frozendict import FrozenDict
from shoalsoft.pants_opentelemetry_plugin.message_protocol import (
    CompleteWorkunitData,
    FinishData,
    InitializeData,
    OtelParameters,
    ProcessorMessage,
    ProcessorMessageDataT,
    ProcessorOperation,
    StartWorkunitData,
)
from shoalsoft.pants_opentelemetry_plugin.processor import (
    IncompleteWorkunit,
    Processor,
    ProcessorContext,
    Workunit,
)

logger = logging.getLogger(__name__)


class SubprocessProcessor(Processor):
    """A processor that offloads OpenTelemetry operations to a subprocess in
    order to avoid fork safety issues with the gRPC C libary."""

    def __init__(
        self,
        *,
        otel_parameters: OtelParameters,
        build_root: str,
        traceparent_env_var: str | None,
    ) -> None:
        self._otel_parameters = otel_parameters
        self._build_root = build_root
        self._traceparent_env_var = traceparent_env_var

        self.subprocess: subprocess.Popen | None = None
        self._writer_lock = threading.Lock()
        self._sequence_reader_thread: threading.Thread | None = None
        self._stderr_reader_thread: threading.Thread | None = None

        self._next_sequence_id = 0
        self._last_processed_sequence_id = 0
        self._last_processed_sequence_id_cond = threading.Condition()

        self._shutdown_event = threading.Event()
        self.initialized = False

    def _get_next_sequence_id(self) -> int:
        self._next_sequence_id += 1
        return self._next_sequence_id

    def _write_length_prefixed_message(self, message: ProcessorMessage) -> None:
        """Write a length-prefixed message to the sidecar process."""
        if self.subprocess is None or self.subprocess.stdin is None:
            logger.warning("Cannot write message: subprocess stdin not available")
            return

        encoded_message = pickle.dumps(message)

        try:
            length = len(encoded_message)
            length_bytes = struct.pack(">I", length)

            with self._writer_lock:
                self.subprocess.stdin.write(length_bytes)
                self.subprocess.stdin.write(encoded_message)
                self.subprocess.stdin.flush()

            logger.debug(f"Wrote message of length {length}")

        except Exception as e:
            logger.error(f"Error writing message: {e}")
            raise

    def _send_msg(self, message: ProcessorMessage) -> None:
        logger.debug(f"Sending message {message.operation} with sequence ID {message.sequence_id}")
        if self.subprocess is None or self.subprocess.stdin is None:
            logger.warning("Cannot enqueue message: sidecar not available")
            return

        if self._shutdown_event.is_set():
            logger.debug("Ignoring enqueue after shutdown")
            return

        try:
            self._write_length_prefixed_message(message)

        except Exception as e:
            logger.error(f"Error enqueueing message: {e}")

    def _read_sequence_ids_task(self, started_event: threading.Event) -> None:
        logger.debug("Starting sequence reader task")

        # Check if we even have a reader
        if not self.subprocess or not self.subprocess.stdout:
            logger.error("No reader available!")
            started_event.set()  # Signal that we've started even if we're failing
            return

        # Signal that the thread has started
        started_event.set()

        try:
            while not self._shutdown_event.is_set():

                try:
                    # Check if subprocess is still alive before attempting to read
                    if self.subprocess.poll() is not None:
                        logger.error(
                            f"Subprocess has terminated with code {self.subprocess.returncode}"
                        )
                        break

                    # Read exactly 4 bytes for sequence ID
                    seq_num_bytes = self.subprocess.stdout.read(4)
                    if not seq_num_bytes:
                        logger.debug("No more data from subprocess")
                        break

                    if len(seq_num_bytes) != 4:
                        logger.error(f"Expected 4 bytes, got {len(seq_num_bytes)}")
                        continue

                except Exception as e:
                    logger.error(f"Error reading sequence ID: {e}")
                    # Check if subprocess is still alive
                    if self.subprocess:
                        returncode = self.subprocess.poll()
                        if returncode is not None:
                            logger.error(f"Subprocess died with returncode {returncode}")
                            break
                    continue

                try:
                    values = struct.unpack(">I", seq_num_bytes)
                    seq_num: int = values[0]
                    logger.debug(f"Received sequence ID {seq_num}")

                    with self._last_processed_sequence_id_cond:
                        if seq_num > self._last_processed_sequence_id:
                            self._last_processed_sequence_id = seq_num
                            self._last_processed_sequence_id_cond.notify_all()
                except Exception as e:
                    logger.error(f"Error processing sequence ID: {e}")
                    continue

        except Exception as e:
            logger.error(f"Error reading sequence IDs: {e}")
            raise
        finally:
            logger.debug("Sequence reader task ending")

    def _read_stderr_task(self, started_event: threading.Event) -> None:
        """Read stderr from subprocess and log it."""
        logger.debug("Starting stderr reader task")
        if not self.subprocess or not self.subprocess.stderr:
            logger.error("No stderr reader available!")
            return
        started_event.set()
        try:
            while not self._shutdown_event.is_set():
                line = self.subprocess.stderr.readline()
                if not line:
                    continue
                # Decode and strip the line, then log it
                stderr_msg = line.decode("utf-8", errors="replace").rstrip("\n\r")
                if stderr_msg:  # Only log non-empty lines
                    logger.debug(f"subprocess processor: stderr: {stderr_msg}")
        except Exception as e:
            logger.error(f"Error reading subprocess stderr: {e}")
        finally:
            logger.debug("Stderr reader task ending")

    def is_shutdown(self) -> bool:
        """Check if queue has shutdown."""
        return self._shutdown_event.is_set()

    def wait_for_shutdown(self, timeout: Optional[float] = None) -> bool:
        """Wait for queue to shutdown, returns True if shutdown completed."""
        return self._shutdown_event.wait(timeout=timeout)

    def _spawn_subprocess(self) -> None:
        """Start the subprocess which will actually invoke gRPC APIs."""
        logger.debug("Starting subprocess")

        try:
            args = [
                sys.executable,
                str(Path(__file__).parent.joinpath("otlp_grpc_subprocess_processor_server.py")),
                "--build_root",
                self._build_root,
                *(
                    [f"--traceparent_env_var={self._traceparent_env_var}"]
                    if self._traceparent_env_var
                    else []
                ),
                *self._otel_parameters.to_args_for_subprocess(),
            ]
            self.subprocess = subprocess.Popen(
                args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env={
                    "PYTHONPATH": ":".join(sys.path),
                    "PYTHONUNBUFFERED": "1",
                },
            )
            logger.debug(f"Subprocess created with PID {self.subprocess.pid}")
            sequence_reader_started_event = threading.Event()
            stderr_reader_started_event = threading.Event()

            self._sequence_reader_thread = threading.Thread(
                target=self._read_sequence_ids_task,
                args=(sequence_reader_started_event,),
                daemon=True,
            )
            self._stderr_reader_thread = threading.Thread(
                target=self._read_stderr_task, args=(stderr_reader_started_event,), daemon=True
            )

            self._sequence_reader_thread.start()
            self._stderr_reader_thread.start()

            # Wait for threads to start.
            if not sequence_reader_started_event.wait(timeout=5.0):
                logger.error("Timeout while waiting for sequence reader thread to start.")
                raise RuntimeError("Failed to start sequence ID reader thread.")
            if not stderr_reader_started_event.wait(timeout=5.0):
                logger.error("Timeout while waiting for stderr reader thread to start.")
                raise RuntimeError("Failed to start stderr reader thread.")

            # Check if subprocess is still alive after brief initialization
            if self.subprocess.poll() is not None:
                logger.error(
                    f"Subprocess died immediately after start (exit code: {self.subprocess.returncode})"
                )
                raise RuntimeError(
                    f"Subprocess failed to start (exit code: {self.subprocess.returncode})"
                )

            logger.debug(f"gRPC processor subprocess started with PID {self.subprocess.pid}")

        except Exception as e:
            logger.error(f"Failed to start subprocess for gRPC OpenTelemetry handler: {e}")
            raise

    def _kill_subprocess(self) -> None:
        if not self.subprocess:
            return

        # Set shutdown event to signal threads to stop
        self._shutdown_event.set()

        # Join the reader threads
        if self._sequence_reader_thread and self._sequence_reader_thread.is_alive():
            self._sequence_reader_thread.join(timeout=5.0)
        if self._stderr_reader_thread and self._stderr_reader_thread.is_alive():
            self._stderr_reader_thread.join(timeout=5.0)

        self.subprocess.kill()
        self.subprocess = None

    def enqueue_message(self, operation: ProcessorOperation, data: ProcessorMessageDataT) -> int:
        """Create and enqueue a processor message."""
        message = ProcessorMessage(
            operation=operation,
            data=data,
            sequence_id=self._get_next_sequence_id(),
        )
        self._send_msg(message)
        return message.sequence_id

    def wait_for_sequence_id(self, desired_sequence_id: int) -> None:
        logger.debug(
            f"Waiting for sequence ID {desired_sequence_id}, current: {self._last_processed_sequence_id}"
        )

        # Check if subprocess is still running
        if self.subprocess:
            returncode = self.subprocess.poll()
            if returncode is not None:
                error_msg = (
                    f"Subprocess has exited with code {returncode} before processing sequence ID {desired_sequence_id}. "
                    f"This indicates the subprocess crashed. Check stderr output above for details."
                )
                logger.error(error_msg)
                raise RuntimeError(f"Subprocess exited with code {returncode}")
        else:
            logger.error("No subprocess found when waiting for sequence ID")
            raise RuntimeError("No subprocess found")

        with self._last_processed_sequence_id_cond:
            # Wait for the condition with timeout
            success = self._last_processed_sequence_id_cond.wait_for(
                lambda: self._last_processed_sequence_id >= desired_sequence_id,
                timeout=5.0,
            )

            if not success:
                error_msg = (
                    f"Timeout waiting for sequence ID {desired_sequence_id} "
                    f"(current: {self._last_processed_sequence_id}). "
                )
                logger.error(error_msg)
                raise RuntimeError(f"Timeout waiting for sequence ID {desired_sequence_id}")

        logger.debug(f"Received sequence ID {desired_sequence_id}")

    def initialize(self) -> None:
        logger.debug("Initializing SubprocessProcessor")

        self._spawn_subprocess()

        try:
            initialize_data = InitializeData(
                otel_parameters=self._otel_parameters,
                build_root=self._build_root,
                traceparent_env_var=self._traceparent_env_var,
            )
            seq_num = self.enqueue_message(ProcessorOperation.INITIALIZE, initialize_data)
            self.wait_for_sequence_id(seq_num)

            self.initialized = True
            logger.info("SubprocessProcessor initialized successfully")

        except Exception as e:
            logger.error(f"Error initializing SubprocessProcessor: {e}")
            raise

    def start_workunit(self, workunit: IncompleteWorkunit, *, context: ProcessorContext) -> None:
        """Enqueue start_workunit message."""
        if not self.initialized:
            logger.warning("Cannot start workunit: processor not initialized")
            return

        try:
            data = StartWorkunitData(
                workunit=workunit,
                context_metrics=FrozenDict(context.get_metrics()),
            )
            self.enqueue_message(ProcessorOperation.START_WORKUNIT, data)
        except Exception as e:
            logger.error(f"Error starting workunit: {e}")

    def complete_workunit(self, workunit: Workunit, *, context: ProcessorContext) -> None:
        """Enqueue complete_workunit message."""
        if not self.initialized:
            logger.warning("Cannot complete workunit: processor not initialized")
            return

        try:
            data = CompleteWorkunitData(
                workunit=workunit,
                context_metrics=FrozenDict(context.get_metrics()),
            )
            self.enqueue_message(ProcessorOperation.COMPLETE_WORKUNIT, data)
        except Exception as e:
            logger.error(f"Error completing workunit: {e}")

    def finish(
        self, timeout: datetime.timedelta | None = None, *, context: ProcessorContext
    ) -> None:
        """Enqueue finish message and monitor shutdown."""
        logger.info("SubprocessProcessor finish requested")

        if not self.initialized:
            logger.warning("Cannot finish: processor not initialized")
            return

        try:
            timeout_seconds = timeout.total_seconds() if timeout else None
            data = FinishData(
                timeout_seconds=timeout_seconds,
                context_metrics=FrozenDict(context.get_metrics()),
            )

            finish_seq_num = self.enqueue_message(ProcessorOperation.FINISH, data)
            self.wait_for_sequence_id(finish_seq_num)

            self._kill_subprocess()

        except Exception as e:
            logger.error(f"Error finishing SubprocessProcessor: {e}")
        finally:
            logger.debug("SubprocessProcessor.finish: Finished")
        logger.info("SubprocessProcessor finish completed")
