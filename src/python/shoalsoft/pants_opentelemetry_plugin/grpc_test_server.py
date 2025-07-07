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

"""Standalone gRPC server for testing - runs in separate process to avoid fork safety issues."""

import logging
import multiprocessing
import signal
import time
from concurrent import futures
from typing import Any, Tuple, Union

import grpc  # type: ignore[import-untyped]
from opentelemetry.proto.collector.trace.v1 import trace_service_pb2, trace_service_pb2_grpc


class TestTraceServiceImpl(trace_service_pb2_grpc.TraceServiceServicer):
    def __init__(
        self, results_queue: "multiprocessing.Queue[Union[Tuple[str, int], bytes]]"
    ) -> None:
        self.results_queue = results_queue

    def Export(
        self, request: trace_service_pb2.ExportTraceServiceRequest, context: Any
    ) -> trace_service_pb2.ExportTraceServiceResponse:
        # Send the serialized request to the test process
        del context  # Unused parameter
        serialized_request = request.SerializeToString()
        self.results_queue.put(serialized_request)
        return trace_service_pb2.ExportTraceServiceResponse()


def run_grpc_test_server(
    port: int,
    results_queue: "multiprocessing.Queue[Union[Tuple[str, int], bytes]]",
    ready_event: Any,
) -> None:
    """Run a gRPC server in a separate process."""
    # Ignore SIGINT to let parent handle shutdown
    signal.signal(signal.SIGINT, signal.SIG_IGN)

    server_impl = TestTraceServiceImpl(results_queue)
    grpc_server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
    trace_service_pb2_grpc.add_TraceServiceServicer_to_server(server_impl, grpc_server)

    actual_port = grpc_server.add_insecure_port(f"127.0.0.1:{port}")
    grpc_server.start()

    # Signal that server is ready and provide actual port
    results_queue.put(("READY", actual_port))
    ready_event.set()

    try:
        # Keep server running until told to stop
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        grpc_server.stop(grace=1.0)


class GrpcTestServerManager:
    """Manager for running gRPC test server in separate process."""

    def __init__(self, port: int = 0):
        self.port = port
        self.process: multiprocessing.Process | None = None
        self.results_queue: multiprocessing.Queue[tuple[str, int] | bytes] = multiprocessing.Queue()
        self.ready_event = multiprocessing.Event()
        self.actual_port: int | None = None
        multiprocessing.log_to_stderr(logging.DEBUG)

    def start(self) -> int:
        """Start the gRPC server process and return the actual port."""
        self.process = multiprocessing.Process(
            target=run_grpc_test_server, args=(self.port, self.results_queue, self.ready_event)
        )
        self.process.start()

        # Wait for server to be ready
        if not self.ready_event.wait(timeout=10.0):
            self.stop()
            raise RuntimeError("gRPC test server failed to start within timeout")

        # Get the actual port
        message = self.results_queue.get(timeout=5.0)
        if not isinstance(message, tuple) or message[0] != "READY":
            self.stop()
            raise RuntimeError(f"Unexpected message from server: {message!r}")

        self.actual_port = message[1]
        return self.actual_port

    def get_received_requests(self) -> list[trace_service_pb2.ExportTraceServiceRequest]:
        """Get all received trace requests."""
        requests = []

        # Drain all available messages
        while True:
            try:
                message = self.results_queue.get_nowait()
                if isinstance(message, bytes):
                    # This is a serialized trace request
                    request = trace_service_pb2.ExportTraceServiceRequest()
                    request.ParseFromString(message)
                    requests.append(request)
            except Exception:
                break

        return requests

    def stop(self) -> None:
        """Stop the gRPC server process."""
        if self.process and self.process.is_alive():
            self.process.terminate()
            self.process.join(timeout=5.0)
            if self.process.is_alive():
                self.process.kill()
                self.process.join(timeout=2.0)


if __name__ == "__main__":
    # For standalone testing
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()

    manager = GrpcTestServerManager(args.port)
    try:
        port = manager.start()
        print(f"gRPC server started on port {port}")

        # Keep running until interrupted
        while True:
            time.sleep(1)
            requests = manager.get_received_requests()
            if requests:
                print(f"Received {len(requests)} trace requests")

    except KeyboardInterrupt:
        print("Shutting down...")
    finally:
        manager.stop()
