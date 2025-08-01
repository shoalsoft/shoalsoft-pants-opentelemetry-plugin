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

import json
import logging
import os
import subprocess
import tempfile
import textwrap
import threading
import time
import typing
from dataclasses import dataclass
from functools import partial
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Iterable, Mapping

import httpx
import pytest
from opentelemetry.proto.collector.trace.v1 import trace_service_pb2
from opentelemetry.proto.common.v1 import common_pb2
from opentelemetry.proto.trace.v1 import trace_pb2
from packaging.version import Version

from pants.testutil.python_interpreter_selection import python_interpreter_path
from pants.util.dirutil import safe_file_dump
from shoalsoft.pants_opentelemetry_plugin.pants_integration_testutil import run_pants_with_workdir
from shoalsoft.pants_opentelemetry_plugin.subsystem import TracingExporterId

logger = logging.getLogger(__name__)


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
    assert root_span.links[0].span_id == b"\xbb\xbb\xbb\xbb\xbb\xbb\xbb\xbb"
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
                "--shoalsoft-opentelemetry-enabled",
                f"--shoalsoft-opentelemetry-exporter={TracingExporterId.OTLP.value}",
                f"--shoalsoft-opentelemetry-exporter-endpoint=http://127.0.0.1:{server_port}/v1/traces",
                "list",
                "otlp-http::",
            ],
            pants_exe_args=pants_exe_args,
            workdir=str(workdir),
            extra_env={
                **(extra_env if extra_env else {}),
                "PANTS_BUILDROOT_OVERRIDE": str(buildroot),
                "TRACEPARENT": "00-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-bbbbbbbbbbbbbbbb-00",
            },
            cwd=buildroot,
            stream_output=True,
        )
        result.assert_success()

        # Assert that tracing spans were received over HTTP.
        assert len(recorded_requests) > 0, "No trace requests received!"

        def _convert(body: bytes) -> trace_service_pb2.ExportTraceServiceRequest:
            trace_request = trace_service_pb2.ExportTraceServiceRequest()
            trace_request.ParseFromString(body)
            return trace_request

        _assert_trace_requests([_convert(request.body) for request in recorded_requests])


def do_test_of_json_file_exporter(
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
                "--shoalsoft-opentelemetry-enabled",
                f"--shoalsoft-opentelemetry-exporter={TracingExporterId.JSON_FILE.value}",
                "list",
                "otel-json::",
            ],
            pants_exe_args=pants_exe_args,
            workdir=str(workdir),
            extra_env={
                **(extra_env if extra_env else {}),
                "PANTS_BUILDROOT_OVERRIDE": str(buildroot),
                "TRACEPARENT": "00-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-bbbbbbbbbbbbbbbb-00",
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


@pytest.mark.parametrize("pants_version_str", ["2.28.0a0", "2.27.0", "2.26.2", "2.25.3"])
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

    # Install a venv expanded from the plugin's pex file. (The BUILD file arranges for the pex files to be materialized
    # in the sandbox as dependencies.)
    plugin_venv_path = (Path.cwd() / f"plugin-venv-{pants_major_minor}").resolve()
    plugin_venv_path.mkdir(parents=True)
    plugin_pex_files = [
        name
        for name in os.listdir(Path.cwd())
        if name.startswith(f"shoalsoft-pants-opentelemetry-plugin-pants{pants_major_minor}")
        and name.endswith(".pex")
    ]
    assert (
        len(plugin_pex_files) == 1
    ), f"Expected to find exactly one pex file for Pants {pants_major_minor}."
    subprocess.run(
        [python_path, plugin_pex_files[0], "venv", str(plugin_venv_path)],
        env={"PEX_TOOLS": "1"},
        check=True,
    )
    site_packages_path = (
        plugin_venv_path / "lib" / f"python{py_version_for_pants_major_minor}" / "site-packages"
    )

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
        pythonpath = ["{site_packages_path}"]
        backend_packages = ["pants.backend.python", "shoalsoft.pants_opentelemetry_plugin"]
        print_stacktrace = true
        pantsd = false

        [python]
        interpreter_constraints = "==3.11.*"
        pip_version = "25.0"

        [pex-cli]
        version = "v2.33.9"
        known_versions = [
        "v2.33.9|macos_arm64|cfd9eb9bed9ac3c33d7da632a38973b42d2d77afe9fdef65dd43b53d0eeb4a98|4678343",
        "v2.33.9|macos_x86_64|cfd9eb9bed9ac3c33d7da632a38973b42d2d77afe9fdef65dd43b53d0eeb4a98|4678343",
        "v2.33.9|linux_x86_64|cfd9eb9bed9ac3c33d7da632a38973b42d2d77afe9fdef65dd43b53d0eeb4a98|4678343",
        "v2.33.9|linux_arm64|cfd9eb9bed9ac3c33d7da632a38973b42d2d77afe9fdef65dd43b53d0eeb4a98|4678343",
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

    with subtests.test(msg="OTEL/JSON file span exporter"):
        do_test_of_json_file_exporter(
            buildroot=buildroot,
            pants_exe_args=pants_exe_args,
            workdir_base=workdir_base,
            extra_env=extra_env,
        )
