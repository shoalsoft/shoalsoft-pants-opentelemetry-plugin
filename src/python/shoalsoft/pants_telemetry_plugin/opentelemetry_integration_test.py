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
    sources = {
        "pants.toml": textwrap.dedent(
            """\
            [GLOBAL]
            pants_version = "2.24.0"
            backend_packages.add = ["pants.backend.python", "shoalsoft.pants_telemetry_plugin"]
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
                f"--shoalsoft-exporters=['{TracingExporterId.OTEL_JSON_FILE}']",
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

        traces_content = trace_file.read_text()
        for trace_line in traces_content.splitlines():
            trace_json = json.loads(trace_line)
            assert "name" in trace_json
