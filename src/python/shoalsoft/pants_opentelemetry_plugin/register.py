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

import datetime
import logging

from pants.base.build_root import BuildRoot
from pants.engine.env_vars import EnvironmentVars, EnvironmentVarsRequest
from pants.engine.rules import Get, collect_rules, rule
from pants.engine.streaming_workunit_handler import (
    WorkunitsCallbackFactory,
    WorkunitsCallbackFactoryRequest,
)
from pants.engine.unions import UnionRule
from shoalsoft.pants_opentelemetry_plugin.exception_logging_processor import (
    ExceptionLoggingProcessor,
)
from shoalsoft.pants_opentelemetry_plugin.opentelemetry import get_processor
from shoalsoft.pants_opentelemetry_plugin.processor import Processor
from shoalsoft.pants_opentelemetry_plugin.single_threaded_processor import SingleThreadedProcessor
from shoalsoft.pants_opentelemetry_plugin.subsystem import TelemetrySubsystem
from shoalsoft.pants_opentelemetry_plugin.workunit_handler import TelemetryWorkunitsCallback

logger = logging.getLogger(__name__)


class TelemetryWorkunitsCallbackFactoryRequest(WorkunitsCallbackFactoryRequest):
    pass


@rule
async def telemetry_workunits_callback_factory_request(
    _: TelemetryWorkunitsCallbackFactoryRequest,
    telemetry: TelemetrySubsystem,
    build_root: BuildRoot,
) -> WorkunitsCallbackFactory:
    processor: Processor | None = None
    if telemetry.enabled and telemetry.exporter:
        traceparent_env_var: str | None = None
        if telemetry.parse_traceparent:
            env_vars = await Get(EnvironmentVars, EnvironmentVarsRequest(["TRACEPARENT"]))
            traceparent_env_var = env_vars.get("TRACEPARENT")

        otel_processor = get_processor(
            span_exporter_name=telemetry.exporter,
            telemetry=telemetry,
            build_root=build_root.pathlib_path,
            traceparent_env_var=traceparent_env_var,
        )

        processor = SingleThreadedProcessor(
            ExceptionLoggingProcessor(otel_processor, name="OpenTelemetry")
        )
        processor.initialize()

    finish_timeout = datetime.timedelta(seconds=telemetry.finish_timeout)
    return WorkunitsCallbackFactory(
        lambda: (
            TelemetryWorkunitsCallback(
                processor=processor,
                finish_timeout=finish_timeout,
                async_completion=telemetry.async_completion,
            )
            if processor is not None
            else None
        )
    )


def rules():
    return (
        *collect_rules(),
        UnionRule(WorkunitsCallbackFactoryRequest, TelemetryWorkunitsCallbackFactoryRequest),
    )
