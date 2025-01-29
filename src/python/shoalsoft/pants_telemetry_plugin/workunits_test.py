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
from typing import Any, Mapping

import pytest

from pants.engine.rules import QueryRule
from pants.engine.streaming_workunit_handler import WorkunitsCallbackFactory
from pants.testutil.rule_runner import RuleRunner
from pants.util.dirutil import safe_file_dump
from shoalsoft.pants_telemetry_plugin import register
from shoalsoft.pants_telemetry_plugin.pants_integration_testutil import run_pants_with_workdir
from shoalsoft.pants_telemetry_plugin.register import TelemetryWorkunitsCallbackFactoryRequest
from shoalsoft.pants_telemetry_plugin.workunits import TelemetryWorkunitsCallback


@pytest.fixture
def rule_runner() -> RuleRunner:
    rule_runner = RuleRunner(
        rules=(
            *register.rules(),
            QueryRule(WorkunitsCallbackFactory, (TelemetryWorkunitsCallbackFactoryRequest,)),
        ),
    )
    rule_runner.set_options(["--shoalsoft-telemetry-enabled"])
    return rule_runner


def test_telemetry_basic_setup(rule_runner):
    callback_factory = rule_runner.request(
        WorkunitsCallbackFactory, [TelemetryWorkunitsCallbackFactoryRequest()]
    )
    callback = callback_factory.callback_factory()
    assert callback is not None
    assert isinstance(callback, TelemetryWorkunitsCallback)


def safe_write_files(base_path: str, files: Mapping[str, str | bytes]) -> None:
    for name, content in files.items():
        safe_file_dump(os.path.join(base_path, name), content, makedirs=True)


def _read_workunits(path: os.PathLike) -> list[dict[Any, Any]]:
    result = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            result.append(json.loads(line.strip()))
    return result


_WORKUNIT_TYPES = {
    "name": (True, str),
    "span_id": (True, str),
    "parent_ids": (True, list),
    "level": (True, str),
    "description": (True, str),
    "start_secs": (True, int),
    "start_nanos": (True, int),
    "duration_secs": (True, int),
    "duration_nanos": (True, int),
    "metadata": (True, dict),
    "artifacts": (True, dict),
    "counters": (False, dict),
}


def _assert_workunit_types(workunit: dict[Any, Any]) -> None:
    for field_name, (required, field_type) in _WORKUNIT_TYPES.items():
        if field_name not in workunit:
            if required:
                raise AssertionError(
                    f"Workunit field `{field_name}` not found in workunit: {workunit}"
                )
            continue
        field_value = workunit[field_name]
        if not isinstance(field_value, field_type):
            raise AssertionError(
                f"Unexpected type for workunit field `{field_name}`; expected: `{field_type}`, actual: `{type(field_value)}`."
            )


def test_workunits_are_output() -> None:
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
        safe_write_files(buildroot, sources)
        result = run_pants_with_workdir(
            ["--shoalsoft-telemetry-enabled", "list", "::"],
            workdir=str(workdir),
            extra_env={
                "PANTS_BUILDROOT_OVERRIDE": str(buildroot),
            },
            hermetic=False,
            cwd=buildroot,
        )
        result.assert_success()
        dist_dir = Path(buildroot) / "dist"
        dist_files = os.listdir(dist_dir)
        assert "workunits.log-started" in dist_files
        assert "workunits.log-completed" in dist_files
        completed_workunits = _read_workunits(dist_dir / "workunits.log-completed")
        for workunit in completed_workunits:
            if not workunit:
                continue
            _assert_workunit_types(workunit)
