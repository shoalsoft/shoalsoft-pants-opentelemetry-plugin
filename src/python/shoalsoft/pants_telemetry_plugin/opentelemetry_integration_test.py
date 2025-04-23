# Copyright (C) 2025 Shoal Software LLC. All rights reserved.
#
# This is commercial software and cannot be used without prior permission.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

from __future__ import annotations

import json
import os
import shutil
import tempfile
import textwrap
import threading
import time
import typing
from concurrent import futures
from dataclasses import dataclass
from functools import partial
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Iterable, Mapping

import grpc  # type: ignore[import-untyped]
import httpx
import pytest
from opentelemetry.proto.collector.trace.v1 import trace_service_pb2, trace_service_pb2_grpc
from opentelemetry.proto.common.v1 import common_pb2
from opentelemetry.proto.trace.v1 import trace_pb2
from packaging.version import Version

from pants.testutil.python_interpreter_selection import python_interpreter_path
from pants.util.dirutil import safe_file_dump
from shoalsoft.pants_telemetry_plugin.pants_integration_testutil import run_pants_with_workdir
from shoalsoft.pants_telemetry_plugin.subsystem import TracingExporterId


def _safe_write_files(base_path: str | os.PathLike, files: Mapping[str, str | bytes]) -> None:
    for name, content in files.items():
        safe_file_dump(os.path.join(base_path, name), content, makedirs=True)


@dataclass(frozen=True)
class RecordedRequest:
    method: str
    path: str
    body: bytes


class _RequestRecorder(BaseHTTPRequestHandler):
    def __init__(self, *args, requests: list[RecordedRequest], **kwargs) -> None:
        self.requests = requests
        super().__init__(*args, **kwargs)

    def do_GET(self):
        self.send_response(200)
        self.end_headers()

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(content_length)

        received_request = RecordedRequest(method=self.command, path=self.path, body=body)
        self.requests.append(received_request)

        self.send_response(200)
        self.end_headers()


def _wait_for_server_availability(port: int, *, num_attempts: int = 4) -> None:
    url = f"http://127.0.0.1:{port}/"
    while num_attempts > 0:
        try:
            r = httpx.get(url)
            if r.status_code == 200:
                break
        except httpx.ConnectError:
            pass

        num_attempts -= 1
        time.sleep(0.15)

    if num_attempts <= 0:
        raise Exception("HTTP server did not startup.")


def _get_span_attr(span: trace_pb2.Span, key: str) -> common_pb2.KeyValue | None:
    for attr in span.attributes:
        if attr.key == key:
            return typing.cast(common_pb2.KeyValue, attr)
    return None


def _assert_trace_requests(requests: Iterable[trace_service_pb2.ExportTraceServiceRequest]) -> None:
    root_span: trace_pb2.Span | None = None
    for request in requests:
        for resource_span in request.resource_spans:

            def _get_resouce_span_attr(key: str) -> common_pb2.KeyValue | None:
                for attr in resource_span.resource.attributes:
                    if attr.key == key:
                        return typing.cast(common_pb2.KeyValue, attr)
                return None

            service_name_attr = _get_resouce_span_attr("service.name")
            assert service_name_attr is not None, "Missing service.name attribute in resource span."
            assert service_name_attr.value.string_value == "pantsbuild"

            for scope_span in resource_span.scope_spans:
                for span in scope_span.spans:
                    if not span.parent_span_id:
                        assert root_span is None, "Found multiple candidate root spans."
                        root_span = span

                    workunit_level_attr = _get_span_attr(span, "pantsbuild.workunit.level")
                    assert (
                        workunit_level_attr is not None
                    ), "Missing workunit.level attribute in span."

                    workunit_span_id_attr = _get_span_attr(span, "pantsbuild.workunit.span_id")
                    assert (
                        workunit_span_id_attr is not None
                    ), "Missing workunit.span_id attribute in span."

    assert root_span is not None, "No root span found."
    assert (
        root_span.links[0].trace_id
        == b"\xaa\xaa\xaa\xaa\xaa\xaa\xaa\xaa\xaa\xaa\xaa\xaa\xaa\xaa\xaa\xaa"
    )
    metrics_attr = _get_span_attr(root_span, "pantsbuild.metrics-v0")
    assert metrics_attr is not None, "Missing metrics attribute in root span."


def do_test_of_otlp_http_exporter(
    *,
    buildroot: Path,
    pants_exe_args: Iterable[str],
    workdir_base: Path,
    extra_env: Mapping[str, str] | None = None,
) -> None:
    recorded_requests: list[RecordedRequest] = []
    server_handler = partial(_RequestRecorder, requests=recorded_requests)
    http_server = HTTPServer(("127.0.0.1", 0), server_handler)
    server_port = http_server.server_port

    def _server_thread_func() -> None:
        http_server.serve_forever()

    server_thread = threading.Thread(target=_server_thread_func)
    server_thread.daemon = True
    server_thread.start()

    _wait_for_server_availability(server_port)

    sources = {
        "otlp-http/BUILD": "python_sources(name='src')\n",
        "otlp-http/main.py": "print('Hello World!)\n",
    }
    with tempfile.TemporaryDirectory(dir=workdir_base) as workdir:
        _safe_write_files(buildroot, sources)

        result = run_pants_with_workdir(
            [
                "--shoalsoft-telemetry-enabled",
                f"--shoalsoft-telemetry-exporter={TracingExporterId.OTLP_HTTP.value}",
                f"--shoalsoft-telemetry-otel-exporter-endpoint=http://127.0.0.1:{server_port}/v1/traces",
                "--shoalsoft-telemetry-otel-parent-trace-id=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "list",
                "otlp-http::",
            ],
            pants_exe_args=pants_exe_args,
            workdir=str(workdir),
            extra_env={
                **(extra_env if extra_env else {}),
                "PANTS_BUILDROOT_OVERRIDE": str(buildroot),
            },
            cwd=buildroot,
            stream_output=True,
        )
        result.assert_success()

        # Assert that tracing spans were received over HTTP.
        assert len(recorded_requests) > 0

        def _convert(body: bytes) -> trace_service_pb2.ExportTraceServiceRequest:
            trace_request = trace_service_pb2.ExportTraceServiceRequest()
            trace_request.ParseFromString(body)
            return trace_request

        _assert_trace_requests([_convert(request.body) for request in recorded_requests])


class _TraceServiceImpl(trace_service_pb2_grpc.TraceServiceServicer):
    def __init__(self, requests: list[trace_service_pb2.ExportTraceServiceRequest]) -> None:
        self.requests = requests

    def Export(
        self, request: trace_service_pb2.ExportTraceServiceRequest, context
    ) -> trace_service_pb2.ExportTraceServiceResponse:
        self.requests.append(request)
        return trace_service_pb2.ExportTraceServiceResponse()


def do_test_of_otlp_grpc_exporter(
    *,
    buildroot: Path,
    pants_exe_args: Iterable[str],
    workdir_base: Path,
    extra_env: Mapping[str, str] | None = None,
) -> None:
    received_requests: list[trace_service_pb2.ExportTraceServiceRequest] = []
    server_impl = _TraceServiceImpl(received_requests)

    grpc_server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
    trace_service_pb2_grpc.add_TraceServiceServicer_to_server(server_impl, grpc_server)
    server_port = grpc_server.add_insecure_port("127.0.0.1:0")
    grpc_server.start()

    sources = {
        "otlp-grpc/BUILD": "python_sources(name='src')\n",
        "otlp-grpc/main.py": "print('Hello World!)\n",
    }
    with tempfile.TemporaryDirectory(dir=workdir_base) as workdir:
        _safe_write_files(buildroot, sources)

        result = run_pants_with_workdir(
            [
                "--shoalsoft-telemetry-enabled",
                f"--shoalsoft-telemetry-exporter={TracingExporterId.OTLP_GRPC.value}",
                f"--shoalsoft-telemetry-otel-exporter-endpoint=http://127.0.0.1:{server_port}/",
                "--shoalsoft-telemetry-otel-exporter-insecure",
                "--shoalsoft-telemetry-otel-parent-trace-id=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "list",
                "otlp-grpc::",
            ],
            pants_exe_args=pants_exe_args,
            workdir=workdir,
            extra_env={
                **(extra_env if extra_env else {}),
                "PANTS_BUILDROOT_OVERRIDE": str(buildroot),
                "GRPC_VERBOSITY": "DEBUG",
            },
            cwd=buildroot,
        )
        result.assert_success()

        # Assert that tracing spans were received over HTTP.
        assert len(received_requests) > 0
        _assert_trace_requests(received_requests)


def do_test_of_otel_json_file_exporter(
    *,
    buildroot: Path,
    pants_exe_args: Iterable[str],
    workdir_base: Path,
    extra_env: Mapping[str, str] | None = None,
) -> None:
    sources = {
        "otel-json/BUILD": "python_sources(name='src')\n",
        "otel-json/main.py": "print('Hello World!)\n",
    }
    with tempfile.TemporaryDirectory(dir=workdir_base) as workdir:
        _safe_write_files(buildroot, sources)

        trace_file = Path(buildroot) / "dist" / "otel-json-trace.jsonl"
        assert not trace_file.exists()

        result = run_pants_with_workdir(
            [
                "--shoalsoft-telemetry-enabled",
                f"--shoalsoft-telemetry-exporter={TracingExporterId.OTEL_JSON_FILE.value}",
                "--shoalsoft-telemetry-otel-parent-trace-id=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "list",
                "otel-json::",
            ],
            pants_exe_args=pants_exe_args,
            workdir=str(workdir),
            extra_env={
                **(extra_env if extra_env else {}),
                "PANTS_BUILDROOT_OVERRIDE": str(buildroot),
            },
            cwd=buildroot,
        )
        result.assert_success()

        # Assert that tracing spans were output.
        traces_content = trace_file.read_text()
        root_span_json: dict[Any, Any] | None = None
        for trace_line in traces_content.splitlines():
            trace_json = json.loads(trace_line)
            assert len(trace_json["context"]["trace_id"]) > 0
            assert len(trace_json["context"]["span_id"]) > 0
            assert trace_json["resource"]["attributes"]["service.name"] == "pantsbuild"
            if trace_json.get("parent_id") is None:
                assert root_span_json is None, "Found multiple candidate root spans."
                root_span_json = trace_json

        assert root_span_json is not None, "No root span found."
        assert (
            root_span_json["links"][0]["context"]["trace_id"]
            == "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        )


@pytest.mark.parametrize("pants_version_str", ["2.25.1", "2.24.3", "2.23.2", "2.21.2"])
def test_opentelemetry_integration(subtests, pants_version_str: str) -> None:
    pants_version = Version(pants_version_str)
    pants_major_minor = f"{pants_version.major}.{pants_version.minor}"

    # Find the Python interpreter compatible with this version of Pants.
    py_version_for_pants_major_minor = (
        "3.11" if Version(pants_major_minor) >= Version("2.25") else "3.9"
    )
    python_path = python_interpreter_path(py_version_for_pants_major_minor)
    assert (
        python_path
    ), f"Did not find a compatible Python interpreter for test: Pants v{pants_major_minor}"

    # Move the plugin's wheels into a subdirectory. (The BUILD file arranges for the wheels to be materialized
    # in the sandbox as a dependency.)
    plugin_wheels_path = (Path.cwd() / f"wheels-{pants_major_minor}").resolve()
    plugin_wheels_path.mkdir(parents=True)
    for filename in [
        p for p in os.listdir(Path.cwd()) if p.endswith(".whl") and pants_major_minor in p
    ]:
        shutil.copy(filename, plugin_wheels_path)

    # A pex of the Pants version in this resolve is materialised as `pants-MAJOR.MINOR.pex` in the sandbox.
    # This is done to isolate the test environment's virtualenv from the Pants under test.
    pants_pex_path = (Path.cwd() / f"pants-{pants_major_minor}.pex").resolve()
    assert pants_pex_path.exists(), f"Expected to find pants-{pants_major_minor}.pex in sandbox."

    buildroot = (Path.cwd() / f"buildroot-{pants_major_minor}").resolve()
    buildroot.mkdir(parents=True)

    # Write out common configuration file for all integration tests.
    safe_file_dump(
        str(buildroot / "pants.toml"),
        textwrap.dedent(
            f"""\
        [GLOBAL]
        pants_version = "{pants_version}"
        backend_packages = ["pants.backend.python", "shoalsoft.pants_telemetry_plugin"]
        print_stacktrace = true
        plugins = ["shoalsoft-pants-telemetry-plugin-pants{pants_major_minor}==0.0.1"]
        pantsd = false

        [python-repos]
        find_links = [
            "file://{plugin_wheels_path}/",
            "https://wheels.pantsbuild.org/simple/",
        ]

        [python]
        interpreter_constraints = "==3.9.*"
        pip_version = "25.0"

        [pex-cli]
        version = "v2.32.1"
        known_versions = [
          "v2.32.1|macos_arm64|1e953b668ae930e0472e8a40709adbf7c342de9ad249d8bbbc719dce7e50e0f7|4450314",
          "v2.32.1|macos_x86_64|1e953b668ae930e0472e8a40709adbf7c342de9ad249d8bbbc719dce7e50e0f7|4450314",
          "v2.32.1|linux_x86_64|1e953b668ae930e0472e8a40709adbf7c342de9ad249d8bbbc719dce7e50e0f7|4450314",
          "v2.32.1|linux_arm64|1e953b668ae930e0472e8a40709adbf7c342de9ad249d8bbbc719dce7e50e0f7|4450314",
        ]
        """
        ),
    )

    pants_exe_args = [str(pants_pex_path)]
    extra_env = {"PEX_PYTHON": python_path}

    # Force Pants to resolve the plugin.
    workdir_base = buildroot / ".pants.d" / "workdirs"
    workdir_base.mkdir(parents=True)
    with tempfile.TemporaryDirectory(dir=workdir_base) as workdir:
        result = run_pants_with_workdir(
            ["--version"],
            pants_exe_args=pants_exe_args,
            cwd=buildroot,
            workdir=workdir,
            extra_env=extra_env,
        )
        result.assert_success()

    with subtests.test(msg="OTLP/HTTP span exporter"):
        do_test_of_otlp_http_exporter(
            buildroot=buildroot,
            pants_exe_args=pants_exe_args,
            workdir_base=workdir_base,
            extra_env=extra_env,
        )

    with subtests.test(msg="OTLP/GRPC span exporter"):
        do_test_of_otlp_grpc_exporter(
            buildroot=buildroot,
            pants_exe_args=pants_exe_args,
            workdir_base=workdir_base,
            extra_env=extra_env,
        )

    with subtests.test(msg="OTEL/JSON file span exporter"):
        do_test_of_otel_json_file_exporter(
            buildroot=buildroot,
            pants_exe_args=pants_exe_args,
            workdir_base=workdir_base,
            extra_env=extra_env,
        )
