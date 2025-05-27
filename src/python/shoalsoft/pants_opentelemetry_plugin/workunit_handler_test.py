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

import pytest

from pants.engine.rules import QueryRule
from pants.engine.streaming_workunit_handler import WorkunitsCallbackFactory
from pants.testutil.rule_runner import RuleRunner
from shoalsoft.pants_opentelemetry_plugin import register
from shoalsoft.pants_opentelemetry_plugin.register import TelemetryWorkunitsCallbackFactoryRequest
from shoalsoft.pants_opentelemetry_plugin.subsystem import TracingExporterId
from shoalsoft.pants_opentelemetry_plugin.workunit_handler import TelemetryWorkunitsCallback


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
            "--shoalsoft-opentelemetry-enabled",
            f"--shoalsoft-opentelemetry-exporter={TracingExporterId.JSON_FILE.value}",
        ]
    )
    return rule_runner


def test_workunit_callback_factory_setup(rule_runner: RuleRunner) -> None:
    callback_factory = rule_runner.request(
        WorkunitsCallbackFactory, [TelemetryWorkunitsCallbackFactoryRequest()]
    )
    callback = callback_factory.callback_factory()
    assert callback is not None
    assert isinstance(callback, TelemetryWorkunitsCallback)
