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
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
from shoalsoft.pants_opentelemetry_plugin.multiprocessing_processor import MultiprocessingProcessor
from shoalsoft.pants_opentelemetry_plugin.opentelemetry import get_processor
from shoalsoft.pants_opentelemetry_plugin.processor import Processor
from shoalsoft.pants_opentelemetry_plugin.single_threaded_processor import SingleThreadedProcessor
from shoalsoft.pants_opentelemetry_plugin.subsystem import (
    OtelCompression,
    TelemetrySubsystem,
    TracingExporterId,
)
from shoalsoft.pants_opentelemetry_plugin.workunit_handler import TelemetryWorkunitsCallback

logger = logging.getLogger(__name__)


@dataclass
class ProcessorFactoryData:
    """Data class for creating processors in subprocess - must be picklable."""

    span_exporter_name: TracingExporterId
    build_root: Path
    traceparent_env_var: str | None
    # Telemetry config as dict to ensure pickle compatibility
    telemetry_config: dict[str, Any]


def _create_otel_processor(factory_data: ProcessorFactoryData):
    """Module-level factory function for creating OpenTelemetry processors.

    This function must be at module level to be picklable for
    multiprocessing.
    """
    from shoalsoft.pants_opentelemetry_plugin.opentelemetry import get_processor

    # Reconstruct telemetry subsystem from config
    telemetry = _reconstruct_telemetry_subsystem(factory_data.telemetry_config)

    return get_processor(
        span_exporter_name=factory_data.span_exporter_name,
        telemetry=telemetry,
        build_root=factory_data.build_root,
        traceparent_env_var=factory_data.traceparent_env_var,
    )


def _reconstruct_telemetry_subsystem(config: dict[str, Any]) -> Any:
    """Reconstruct a TelemetrySubsystem-like object from config dict."""

    class MockTelemetrySubsystem:
        def __init__(self, config: dict[str, Any]):
            for key, value in config.items():
                # Handle enum reconstruction
                if key == "exporter" and isinstance(value, str):
                    value = TracingExporterId(value)
                elif key == "exporter_compression" and isinstance(value, str):
                    value = OtelCompression(value)
                setattr(self, key, value)

    return MockTelemetrySubsystem(config)


def _serialize_telemetry_config(telemetry: TelemetrySubsystem) -> dict[str, Any]:
    """Extract serializable configuration from TelemetrySubsystem."""
    config = {}

    # Extract all relevant attributes
    attrs_to_serialize = [
        "enabled",
        "exporter",
        "exporter_endpoint",
        "exporter_headers",
        "exporter_timeout",
        "exporter_compression",
        "exporter_insecure",
        "exporter_certificate_file",
        "exporter_client_key_file",
        "exporter_client_certificate_file",
        "json_file",
        "parse_traceparent",
        "finish_timeout",
        "async_completion",
    ]

    for attr in attrs_to_serialize:
        if hasattr(telemetry, attr):
            value = getattr(telemetry, attr)
            # Handle enum serialization
            if hasattr(value, "value"):
                config[attr] = value.value
            else:
                config[attr] = value

    return config


class TelemetryWorkunitsCallbackFactoryRequest(WorkunitsCallbackFactoryRequest):
    pass


@rule
async def telemetry_workunits_callback_factory_request(
    _: TelemetryWorkunitsCallbackFactoryRequest,
    telemetry: TelemetrySubsystem,
    build_root: BuildRoot,
) -> WorkunitsCallbackFactory:
    processor: Processor | None = None
    logger.debug(
        f"telemetry_workunits_callback_factory_request: telemetry.enabled={telemetry.enabled}; telemetry.exporter={telemetry.exporter}; "
        f"bool(telemetry.exporter)={bool(telemetry.exporter)}"
    )
    if telemetry.enabled and telemetry.exporter:
        logger.debug("Enabling OpenTelemetry work unit handler.")

        traceparent_env_var: str | None = None
        if telemetry.parse_traceparent:
            env_vars = await Get(EnvironmentVars, EnvironmentVarsRequest(["TRACEPARENT"]))
            traceparent_env_var = env_vars.get("TRACEPARENT")
            logger.debug(f"Found TRACEPARENT: {traceparent_env_var}")

        # Use multiprocessing processor for gRPC to avoid fork safety issues
        if telemetry.exporter == TracingExporterId.GRPC:
            logger.debug("Using multiprocessing processor for gRPC exporter")

            # Create factory data using dataclass for pickle compatibility
            factory_data = ProcessorFactoryData(
                span_exporter_name=telemetry.exporter,
                build_root=build_root.pathlib_path,
                traceparent_env_var=traceparent_env_var,
                telemetry_config=_serialize_telemetry_config(telemetry),
            )

            processor = MultiprocessingProcessor(
                processor_factory=_create_otel_processor,
                processor_factory_data=factory_data,
            )
        else:
            logger.debug("Using single-threaded processor for non-gRPC exporter")
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
