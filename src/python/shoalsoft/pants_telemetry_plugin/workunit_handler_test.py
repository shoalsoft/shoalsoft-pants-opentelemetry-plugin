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

import pytest

from pants.engine.rules import QueryRule
from pants.engine.streaming_workunit_handler import WorkunitsCallbackFactory
from pants.testutil.rule_runner import RuleRunner
from shoalsoft.pants_telemetry_plugin import register
from shoalsoft.pants_telemetry_plugin.register import TelemetryWorkunitsCallbackFactoryRequest
from shoalsoft.pants_telemetry_plugin.subsystem import TracingExporterId
from shoalsoft.pants_telemetry_plugin.workunit_handler import TelemetryWorkunitsCallback


@pytest.fixture
def rule_runner() -> RuleRunner:
    rule_runner = RuleRunner(
        rules=(
            *register.rules(),
            QueryRule(WorkunitsCallbackFactory, (TelemetryWorkunitsCallbackFactoryRequest,)),
        ),
    )
    rule_runner.set_options(
        [
            "--shoalsoft-telemetry-enabled",
            f"--shoalsoft-exporters=['{TracingExporterId.OTEL_JSON_FILE.value}']",
        ]
    )
    return rule_runner


def test_workunit_callback_factory_setup(rule_runner):
    callback_factory = rule_runner.request(
        WorkunitsCallbackFactory, [TelemetryWorkunitsCallbackFactoryRequest()]
    )
    callback = callback_factory.callback_factory()
    assert callback is not None
    assert isinstance(callback, TelemetryWorkunitsCallback)
