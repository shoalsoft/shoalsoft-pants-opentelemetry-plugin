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
    WorkunitsCallback,
    WorkunitsCallbackFactory,
    WorkunitsCallbackFactoryRequest,
)
from pants.engine.unions import UnionRule
from shoalsoft.pants_opentelemetry_plugin.exception_logging_processor import (
    ExceptionLoggingProcessor,
)
from shoalsoft.pants_opentelemetry_plugin.opentelemetry_config import OtlpParameters
from shoalsoft.pants_opentelemetry_plugin.opentelemetry_processor import get_processor
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
    logger.debug(
        f"telemetry_workunits_callback_factory_request: telemetry.enabled={telemetry.enabled}; telemetry.exporter={telemetry.exporter}; "
        f"bool(telemetry.exporter)={bool(telemetry.exporter)}"
    )

    traceparent_env_var: str | None = None
    if telemetry.enabled and telemetry.exporter and telemetry.parse_traceparent:
        env_vars = await Get(EnvironmentVars, EnvironmentVarsRequest(["TRACEPARENT"]))
        traceparent_env_var = env_vars.get("TRACEPARENT")
        logger.debug(f"Found TRACEPARENT: {traceparent_env_var}")

    def workunits_callback_factory() -> WorkunitsCallback | None:
        if not telemetry.enabled or not telemetry.exporter:
            logger.debug("Skipping enabling OpenTelemetry work unit handler.")
            return None

        logger.debug("Enabling OpenTelemetry work unit handler.")

        otel_processor = get_processor(
            span_exporter_name=telemetry.exporter,
            otlp_parameters=OtlpParameters(
                endpoint=telemetry.exporter_endpoint,
                traces_endpoint=telemetry.exporter_traces_endpoint,
                certificate_file=telemetry.exporter_certificate_file,
                client_key_file=telemetry.exporter_client_key_file,
                client_certificate_file=telemetry.exporter_client_certificate_file,
                headers=telemetry.exporter_headers,
                timeout=telemetry.exporter_timeout,
                compression=(
                    telemetry.exporter_compression.value if telemetry.exporter_compression else None
                ),
            ),
            build_root=build_root.pathlib_path,
            traceparent_env_var=traceparent_env_var,
            json_file=telemetry.json_file,
            trace_link_template=telemetry.trace_link_template,
        )

        processor = SingleThreadedProcessor(
            ExceptionLoggingProcessor(otel_processor, name="OpenTelemetry")
        )

        processor.initialize()

        return TelemetryWorkunitsCallback(
            processor=processor,
            finish_timeout=finish_timeout,
            async_completion=telemetry.async_completion,
        )

    finish_timeout = datetime.timedelta(seconds=telemetry.finish_timeout)
    return WorkunitsCallbackFactory(
        callback_factory=workunits_callback_factory,
    )


def rules():
    return (
        *collect_rules(),
        UnionRule(WorkunitsCallbackFactoryRequest, TelemetryWorkunitsCallbackFactoryRequest),
    )
