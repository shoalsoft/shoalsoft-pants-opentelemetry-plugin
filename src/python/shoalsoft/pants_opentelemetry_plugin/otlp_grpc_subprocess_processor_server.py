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

import argparse
import datetime
import logging
import os
import pickle
import queue
import struct
import sys
import threading
from collections.abc import Mapping, Sequence
from pathlib import Path

from pants.util.frozendict import FrozenDict
from shoalsoft.pants_opentelemetry_plugin.message_protocol import (
    CompleteWorkunitData,
    FinishData,
    InitializeData,
    OtelParameters,
    ProcessorMessage,
    ProcessorOperation,
    StartWorkunitData,
)
from shoalsoft.pants_opentelemetry_plugin.opentelemetry_processor import get_processor
from shoalsoft.pants_opentelemetry_plugin.processor import Processor, ProcessorContext
from shoalsoft.pants_opentelemetry_plugin.subsystem import TracingExporterId


class _Context(ProcessorContext):
    def __init__(self, metrics: FrozenDict[str, int]) -> None:
        self._metrics = metrics

    def get_metrics(self) -> Mapping[str, int]:
        return self._metrics


class Server:
    def __init__(self, processor: Processor) -> None:
        self.processor = processor
        self.message_queue: queue.Queue[ProcessorMessage] = queue.Queue(maxsize=1000)
        self.shutdown_event = threading.Event()
        self.stdin_lock = threading.Lock()
        self.stdout_lock = threading.Lock()

        # Set up logging
        self.pid = os.getpid()
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            handlers=[logging.StreamHandler(sys.stderr)],
        )
        self.logger = logging.getLogger(__name__)
        self.logger.info(f"Sidecar server starting with PID {self.pid}")

    def _read_length_prefixed_message(self) -> bytes | None:
        """Read a length-prefixed message from stdin."""
        try:
            with self.stdin_lock:
                # Read from stdin file descriptor 0 directly
                length_bytes = os.read(0, 4)
                if not length_bytes or len(length_bytes) < 4:
                    self.logger.debug("EOF or incomplete length prefix")
                    return None

                message_length = struct.unpack(">I", length_bytes)[0]
                self.logger.debug(f"Reading message of length {message_length}")

                # Read message data
                message_data = os.read(0, message_length)
                if not message_data or len(message_data) < message_length:
                    self.logger.warning(
                        f"Incomplete message: expected {message_length}, got {len(message_data)}"
                    )
                    return None

                return message_data

        except Exception as e:
            self.logger.error(f"Error reading message: {e}")
            return None

    def message_reader(self) -> None:
        self.logger.info("Starting message reader")

        try:
            while not self.shutdown_event.is_set():
                message_data = self._read_length_prefixed_message()
                if message_data is None:
                    break

                try:
                    message = pickle.loads(message_data)
                    self.message_queue.put(message)

                except Exception as e:
                    self.logger.error(f"Error deserializing message: {e}")
                    continue

        except Exception as e:
            self.logger.error(f"Error in message reader: {e}")
        finally:
            self.logger.info("Message reader shutting down")

    def _handle_shutdown(self) -> None:
        """Handle shutdown message."""
        self.logger.info("Received shutdown message")
        self.shutdown_event.set()

    def _handle_message(self, message: ProcessorMessage) -> None:
        self.logger.debug(f"Processing message: {message.operation}")

        try:
            if message.operation == ProcessorOperation.INITIALIZE:
                data = message.data
                assert isinstance(data, InitializeData)
                self.processor.initialize()
            elif message.operation == ProcessorOperation.START_WORKUNIT:
                data = message.data
                assert isinstance(data, StartWorkunitData)
                self.processor.start_workunit(
                    workunit=data.workunit, context=_Context(data.context_metrics)
                )
            elif message.operation == ProcessorOperation.COMPLETE_WORKUNIT:
                data = message.data
                assert isinstance(data, CompleteWorkunitData)
                self.processor.complete_workunit(
                    workunit=data.workunit, context=_Context(data.context_metrics)
                )
            elif message.operation == ProcessorOperation.FINISH:
                data = message.data
                assert isinstance(data, FinishData)
                self.processor.finish(
                    timeout=datetime.timedelta(seconds=data.timeout_seconds or 1.0),
                    context=_Context(data.context_metrics),
                )
            elif message.operation == ProcessorOperation.SHUTDOWN:
                self._handle_shutdown()
        except Exception as e:
            self.logger.error(
                f"Error while processing work unit message `{message.operation}` (seq id #{message.sequence_id}): {e}"
            )

        # Signal that the message has been processed.
        seq_num = message.sequence_id
        seq_num_bytes = struct.pack(">I", seq_num)
        with self.stdout_lock:
            # Write to stdout file descriptor 1 directly
            os.write(1, seq_num_bytes)

    def process_messages(self) -> None:
        """Process messages received from the parent process."""
        self.logger.info("Starting message processor.")

        try:
            while not self.shutdown_event.is_set():
                try:
                    message = self.message_queue.get(timeout=1.0)
                    self._handle_message(message)
                except queue.Empty:
                    continue
                except Exception as e:
                    self.logger.error(f"Error processing message: {e}")
        finally:
            self.logger.info("Stopped message processor.")

    def run(self) -> None:
        """Main sidecar server loop."""
        self.logger.info("Starting sidecar server")

        try:
            # Start threads
            reader_thread = threading.Thread(target=self.message_reader, daemon=True)
            processor_thread = threading.Thread(target=self.process_messages, daemon=True)

            reader_thread.start()
            processor_thread.start()

            # Wait for shutdown
            self.shutdown_event.wait()

            # Join threads
            reader_thread.join(timeout=5.0)
            processor_thread.join(timeout=5.0)

        except Exception as e:
            self.logger.error(f"Error in sidecar server: {e}")
        finally:
            self.logger.info("Sidecar server shutdown completed")


def main(args: Sequence[str]) -> None:
    parser = argparse.ArgumentParser()
    OtelParameters.add_options_to_parser(parser)
    parser.add_argument("--build_root", default=None, action="store")
    parser.add_argument("--traceparent_env_var", default=None, action="store")
    parsed_options = parser.parse_args(args)
    otel_parameters = OtelParameters.from_parsed_options(parsed_options)

    processor = get_processor(
        span_exporter_name=TracingExporterId.GRPC,
        otel_parameters=otel_parameters,
        build_root=Path(parsed_options.build_root),
        traceparent_env_var=parsed_options.traceparent_env_var,
        json_file=None,
    )

    server = Server(processor)
    server.run()


if __name__ == "__main__":
    main(sys.argv[1:])
