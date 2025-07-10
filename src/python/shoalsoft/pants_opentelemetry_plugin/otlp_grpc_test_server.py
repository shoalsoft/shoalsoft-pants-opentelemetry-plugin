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

import base64
import signal
import sys
from concurrent import futures

import grpc
from opentelemetry.proto.collector.trace.v1 import trace_service_pb2_grpc
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
    ExportTraceServiceResponse,
)


class TraceServiceServicer(trace_service_pb2_grpc.TraceServiceServicer):
    """Receive tracing span export requests for OTLP trace service and pass
    them to callback."""

    def Export(self, request: ExportTraceServiceRequest, context) -> ExportTraceServiceResponse:
        encoded_request = base64.b64encode(request.SerializeToString())
        sys.stdout.buffer.write(encoded_request)
        sys.stdout.buffer.write(b"\n")
        sys.stdout.buffer.flush()
        return ExportTraceServiceResponse()


def main() -> None:
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))

    def stop_handler(signum, frame):
        server.stop(None)

    signal.signal(signal.SIGINT, stop_handler)
    signal.signal(signal.SIGTERM, stop_handler)

    trace_service_pb2_grpc.add_TraceServiceServicer_to_server(TraceServiceServicer(), server)

    port = server.add_insecure_port("127.0.0.1:0")
    sys.stdout.buffer.write(str(port).encode("utf-8") + b"\n")
    sys.stdout.buffer.flush()

    server.start()
    server.wait_for_termination()


if __name__ == "__main__":
    main()
