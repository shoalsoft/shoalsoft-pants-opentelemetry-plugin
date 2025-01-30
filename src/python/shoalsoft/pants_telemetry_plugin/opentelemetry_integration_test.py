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
import tempfile
import textwrap
from pathlib import Path
from typing import Mapping

from pants.util.dirutil import safe_file_dump
from shoalsoft.pants_telemetry_plugin.pants_integration_testutil import run_pants_with_workdir
from shoalsoft.pants_telemetry_plugin.subsystem import TracingExporterId


def _safe_write_files(base_path: str, files: Mapping[str, str | bytes]) -> None:
    for name, content in files.items():
        safe_file_dump(os.path.join(base_path, name), content, makedirs=True)


def test_otel_json_file_exporter() -> None:
    # Location of a copy of the plugin's source code. The BUILD file arranges for the files to materialized
    # in the sandbox as a dependency.
    plugin_python_path = Path.cwd() / "src" / "python"
    assert (plugin_python_path / "shoalsoft" / "pants_telemetry_plugin" / "register.py").exists()

    sources = {
        "pants.toml": textwrap.dedent(
            f"""\
            [GLOBAL]
            pants_version = "2.24.0"
            backend_packages = ["pants.backend.python", "shoalsoft.pants_telemetry_plugin"]
            pythonpath = ['{plugin_python_path}']
            print_stacktrace = true
            """
        ),
        "BUILD": "python_sources(name='src')\n",
        "main.py": "print('Hello World!)\n",
    }
    with tempfile.TemporaryDirectory() as buildroot:
        workdir = Path(buildroot) / ".pants.d" / "the-workdir"
        workdir.mkdir(parents=True)
        _safe_write_files(buildroot, sources)

        trace_file = Path(buildroot) / "dist" / "otel-json-trace.jsonl"
        assert not trace_file.exists()

        result = run_pants_with_workdir(
            [
                "--shoalsoft-telemetry-enabled",
                f"--shoalsoft-telemetry-exporters=['{TracingExporterId.OTEL_JSON_FILE.value}']",
                "list",
                "::",
            ],
            workdir=str(workdir),
            extra_env={
                "PANTS_BUILDROOT_OVERRIDE": str(buildroot),
            },
            hermetic=False,
            cwd=buildroot,
        )
        result.assert_success()

        # Assert that tracing spans were output.
        traces_content = trace_file.read_text()
        for trace_line in traces_content.splitlines():
            trace_json = json.loads(trace_line)
            assert len(trace_json["context"]["trace_id"]) > 0
            assert len(trace_json["context"]["span_id"]) > 0
            assert trace_json["resource"]["attributes"]["service.name"] == "pantsbuild"
