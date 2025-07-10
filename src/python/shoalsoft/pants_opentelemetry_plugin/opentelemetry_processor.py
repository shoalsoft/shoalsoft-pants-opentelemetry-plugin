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
import json
import logging
import typing
import urllib.parse
from pathlib import Path
from typing import TextIO

from grpc import ChannelCredentials as GrpcChannelCredentials
from grpc import Compression as GrpcCompression
from grpc import ssl_channel_credentials
from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter as GrpcOTLPSpanExporter,
)
from opentelemetry.exporter.otlp.proto.http import Compression
from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
    OTLPSpanExporter as HttpOTLPSpanExporter,
)
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider, sampling
from opentelemetry.sdk.trace.export import SpanProcessor  # type: ignore[attr-defined]
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter, SpanExportResult
from opentelemetry.trace import Link, TraceFlags
from opentelemetry.trace.span import NonRecordingSpan, Span, SpanContext
from opentelemetry.trace.status import StatusCode

from pants.util.frozendict import FrozenDict
from shoalsoft.pants_opentelemetry_plugin.message_protocol import OtelParameters
from shoalsoft.pants_opentelemetry_plugin.processor import (
    IncompleteWorkunit,
    Level,
    Processor,
    ProcessorContext,
    Workunit,
)
from shoalsoft.pants_opentelemetry_plugin.subsystem import OtelCompression, TracingExporterId

logger = logging.getLogger(__name__)

_UNIX_EPOCH = datetime.datetime(year=1970, month=1, day=1, tzinfo=datetime.timezone.utc)
_GRPC_COMPRESSION_MAP: dict[OtelCompression, GrpcCompression | None] = {
    OtelCompression.GZIP: GrpcCompression.Gzip,
    OtelCompression.NONE: GrpcCompression.NoCompression,
}


def _datetime_to_otel_timestamp(d: datetime.datetime) -> int:
    """OTEL times are nanoseconds since the Unix epoch."""
    duration_since_epoch = d - _UNIX_EPOCH
    nanoseconds = duration_since_epoch.days * 24 * 60 * 60 * 1000000000
    nanoseconds += duration_since_epoch.seconds * 1000000000
    nanoseconds += duration_since_epoch.microseconds * 1000
    return nanoseconds


class JsonFileSpanExporter(SpanExporter):
    def __init__(self, file: TextIO) -> None:
        self._file = file

    def export(self, spans: typing.Sequence[ReadableSpan]) -> SpanExportResult:
        for span in spans:
            self._file.write(span.to_json(indent=0).replace("\n", " ") + "\n")
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        self._file.close()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        self._file.flush()
        return True


def _read_file(file_path: str, option_name: str) -> bytes:
    try:
        with open(file_path, "rb") as file:
            return file.read()
    except FileNotFoundError as e:
        raise ValueError(
            f"Failed to read file `{e.filename}` obtained from the `{option_name}` option: {e}"
        )


def _get_grpc_credentials(
    otel_parameters: OtelParameters,
) -> GrpcChannelCredentials:
    certificate_file = otel_parameters.certificate_file
    if not certificate_file:
        return ssl_channel_credentials()
    client_key_file = otel_parameters.client_key_file
    client_certificate_file = otel_parameters.client_certificate_file

    root_certificates = (
        _read_file(certificate_file, "--shoalsoft-opentelemetry-exporter-certificate-file")
        if certificate_file
        else None
    )
    private_key = (
        _read_file(client_key_file, "--shoalsoft-opentelemetry-exporter-client-key-file")
        if client_key_file
        else None
    )
    certificate_chain = (
        _read_file(
            client_certificate_file,
            "--shoalsoft-opentelemetry-exporter-client-certificate-file",
        )
        if client_certificate_file
        else None
    )

    return ssl_channel_credentials(
        root_certificates=root_certificates,
        private_key=private_key,
        certificate_chain=certificate_chain,
    )


def _make_span_exporter(name: TracingExporterId, otel_parameters: OtelParameters) -> SpanExporter:
    if name == TracingExporterId.HTTP:
        return HttpOTLPSpanExporter(
            endpoint=otel_parameters.endpoint,
            certificate_file=otel_parameters.certificate_file,
            client_key_file=otel_parameters.client_key_file,
            client_certificate_file=otel_parameters.client_certificate_file,
            headers=dict(otel_parameters.headers) if otel_parameters.headers else None,
            timeout=otel_parameters.timeout,
            compression=Compression(otel_parameters.compression),
        )
    elif name == TracingExporterId.GRPC:
        compression_str = otel_parameters.compression
        compression = OtelCompression(compression_str) if compression_str else None
        if compression is not None and compression not in _GRPC_COMPRESSION_MAP.keys():
            raise ValueError(
                f"OpenTelemetry compression mode `{compression_str}` is not supported for OTLP/gRPC exports."
            )

        credentials: GrpcChannelCredentials | None = None
        if not otel_parameters.insecure:
            credentials = _get_grpc_credentials(otel_parameters)
        elif otel_parameters.endpoint:
            parsed_endpoint = urllib.parse.urlparse(otel_parameters.endpoint)
            if parsed_endpoint.scheme == "https":
                raise ValueError(
                    "`--shoalsoft-opentelemetry-exporter-insecure` is enabled, but the endpoint "
                    f"`{otel_parameters.endpoint}` contains a `https` scheme which "
                    "requires secure mode. Please set `--no-shoalsoft-telemetry-otel-exporter-insecure` "
                    "instead."
                )

        return GrpcOTLPSpanExporter(
            endpoint=otel_parameters.endpoint,
            insecure=otel_parameters.insecure,
            credentials=credentials,
            headers=dict(otel_parameters.headers) if otel_parameters.headers else None,
            timeout=otel_parameters.timeout,
            compression=_GRPC_COMPRESSION_MAP.get(compression) if compression else None,
        )
    else:
        raise AssertionError(f"Unknown OpenTelemetry tracing span exporter: {name}")


def get_processor(
    span_exporter_name: TracingExporterId,
    otel_parameters: OtelParameters,
    build_root: Path,
    traceparent_env_var: str | None,
    json_file: str | None,
) -> Processor:
    resource = Resource(
        attributes={
            SERVICE_NAME: "pantsbuild",
        }
    )
    tracer_provider = TracerProvider(sampler=sampling.ALWAYS_ON, resource=resource)
    tracer = tracer_provider.get_tracer(__name__)

    span_exporter: SpanExporter
    if span_exporter_name == TracingExporterId.JSON_FILE:
        json_file_path_str = json_file
        if not json_file_path_str:
            raise ValueError(
                f"`--shoalsoft-opentelemetry-exporter` is set to `{TracingExporterId.JSON_FILE}` "
                "but the `--shoalsoft-opentelemetry-json-file` option is not set."
            )
        json_file_path = build_root / json_file_path_str
        json_file_path.parent.mkdir(parents=True, exist_ok=True)
        span_exporter = JsonFileSpanExporter(open(json_file_path, "w"))
        logger.debug(f"Enabling OpenTelemetry JSON file span exporter: path={json_file_path}")
    elif span_exporter_name in {TracingExporterId.HTTP, TracingExporterId.GRPC}:
        span_exporter = _make_span_exporter(span_exporter_name, otel_parameters=otel_parameters)
        logger.debug(f"Enabling OpenTelemetry span exporter `{span_exporter_name.value}`.")
    else:
        raise AssertionError(
            f"Asked to construct an unknown span exporter: {span_exporter_name.value}"
        )

    span_processor = BatchSpanProcessor(
        span_exporter=span_exporter,
        max_queue_size=512,
        max_export_batch_size=100,
        export_timeout_millis=5000,
        schedule_delay_millis=30000,
    )
    tracer_provider.add_span_processor(span_processor)

    otel_processor = OpenTelemetryProcessor(
        tracer=tracer, span_processor=span_processor, traceparent_env_var=traceparent_env_var
    )

    return otel_processor


class DummySpan(NonRecordingSpan):
    """A dummy Span used in the thread context so we can trick OpenTelemetry as
    to what the parent span ID is.

    Sets `is_recording` to True.
    """

    def is_recording(self) -> bool:
        return True

    def __repr__(self) -> str:
        return f"DummySpan({self._context!r})"


def _parse_id(id_hex: str, id_hex_chars_len: int) -> int:
    # Remove any potential formatting like hyphens or "0x" prefix
    id_hex = id_hex.replace("-", "").replace("0x", "").lower()

    # Check if the length is correct for the given ID type.
    if len(id_hex) != id_hex_chars_len:
        raise ValueError(
            f"Invalid ID length: expected {id_hex_chars_len} hex chars, got {len(id_hex)} instead."
        )

    # Convert hex string to integer
    return int(id_hex, 16)


def _parse_traceparent(value: str) -> tuple[int, int] | None:
    parts = value.split("-")
    if len(parts) < 3:
        return None

    try:
        trace_id = _parse_id(parts[1], 32)
    except ValueError as e:
        logger.warning(f"Ignoring TRACEPARENT due to failure to parse trace ID `{parts[1]}`: {e}")
        return None

    try:
        span_id = _parse_id(parts[2], 16)
    except ValueError as e:
        logger.warning(f"Ignoring TRACEPARENT due to failure to parse span ID `{parts[2]}`: {e}")
        return None

    return trace_id, span_id


class _Encoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, FrozenDict):
            return o._data
        return super().default(o)


class OpenTelemetryProcessor(Processor):
    def __init__(
        self, tracer: trace.Tracer, span_processor: SpanProcessor, traceparent_env_var: str | None
    ) -> None:
        self._tracer = tracer
        self._trace_id: int | None = None
        self._workunit_span_id_to_otel_span_id: dict[str, int] = {}
        self._otel_spans: dict[int, trace.Span] = {}
        self._span_processor = span_processor
        self._span_count: int = 0
        self._counters: dict[str, int] = {}

        self._parent_trace_id: int | None = None
        self._parent_span_id: int | None = None
        if traceparent_env_var is not None:
            ids = _parse_traceparent(traceparent_env_var)
            if ids is not None:
                self._parent_trace_id = ids[0]
                self._parent_span_id = ids[1]

    def initialize(self) -> None:
        logger.debug("OpenTelemetryProcessor.initialize called")

    def _increment_counter(self, name: str, delta: int = 1) -> None:
        if name not in self._counters:
            self._counters[name] = 0
        self._counters[name] += delta

    def _construct_otel_span(
        self,
        *,
        workunit_span_id: str,
        workunit_parent_span_id: str | None,
        name: str,
        start_time: datetime.datetime,
    ) -> tuple[Span, int]:
        """Construct an OpenTelemetry span.

        Shared between `start_workunit` and `complete_workunit` since
        some spans may arrive already-completed.
        """
        assert workunit_span_id not in self._workunit_span_id_to_otel_span_id

        otel_context = Context()
        if workunit_parent_span_id:
            # OpenTelemetry pulls the parent span ID from the span set as "current" in the supplied context.
            assert self._trace_id is not None
            otel_parent_span_context = SpanContext(
                trace_id=self._trace_id,
                span_id=self._workunit_span_id_to_otel_span_id[workunit_parent_span_id],
                is_remote=False,
            )
            otel_context = trace.set_span_in_context(
                DummySpan(otel_parent_span_context), context=otel_context
            )

        links: list[Link] = []
        if not workunit_parent_span_id and self._parent_trace_id and self._parent_span_id:
            parent_trace_id_context = SpanContext(
                trace_id=self._parent_trace_id,
                span_id=self._parent_span_id,
                is_remote=True,
                trace_flags=TraceFlags(TraceFlags.SAMPLED),
            )
            links.append(Link(context=parent_trace_id_context))

        otel_span = self._tracer.start_span(
            name=name,
            context=otel_context,
            start_time=_datetime_to_otel_timestamp(start_time),
            record_exception=False,
            set_status_on_exception=False,
            links=links,
        )

        # Record the span ID chosen by the tracer for this span.
        otel_span_context = otel_span.get_span_context()
        otel_span_id = otel_span_context.span_id
        self._workunit_span_id_to_otel_span_id[workunit_span_id] = otel_span_id
        self._otel_spans[otel_span_id] = otel_span

        # Record the trace ID generated the first time any span is constructed.
        if self._trace_id is None:
            self._trace_id = otel_span.get_span_context().trace_id

        return otel_span, otel_span_id

    def _apply_incomplete_workunit_attributes(
        self, workunit: IncompleteWorkunit, otel_span: Span
    ) -> None:
        otel_span.set_attribute("pantsbuild.workunit.span_id", workunit.span_id)
        otel_span.set_attribute("pantsbuild.workunit.parent_span_ids", workunit.parent_ids)

        otel_span.set_attribute("pantsbuild.workunit.level", workunit.level.value.upper())
        if workunit.level == Level.ERROR:
            otel_span.set_status(StatusCode.ERROR)

    def _apply_workunit_attributes(self, workunit: Workunit, otel_span: Span) -> None:
        self._apply_incomplete_workunit_attributes(workunit=workunit, otel_span=otel_span)

        for key, value in workunit.metadata.items():
            if isinstance(
                value,
                (
                    str,
                    bool,
                    int,
                    float,
                ),
            ):
                otel_span.set_attribute(f"pantsbuild.workunit.metadata.{key}", value)

    def start_workunit(self, workunit: IncompleteWorkunit, *, context: ProcessorContext) -> None:
        if workunit.span_id in self._workunit_span_id_to_otel_span_id:
            self._increment_counter("multiple_start_workunit_for_span_id")
            return

        otel_span, _ = self._construct_otel_span(
            workunit_span_id=workunit.span_id,
            workunit_parent_span_id=workunit.primary_parent_id,
            name=workunit.name,
            start_time=workunit.start_time,
        )

        self._apply_incomplete_workunit_attributes(workunit=workunit, otel_span=otel_span)

    def complete_workunit(self, workunit: Workunit, *, context: ProcessorContext) -> None:
        otel_span: Span
        otel_span_id: int
        if workunit.span_id in self._workunit_span_id_to_otel_span_id:
            otel_span_id = self._workunit_span_id_to_otel_span_id[workunit.span_id]
            otel_span = self._otel_spans[otel_span_id]
        else:
            otel_span, otel_span_id = self._construct_otel_span(
                workunit_span_id=workunit.span_id,
                workunit_parent_span_id=workunit.primary_parent_id,
                name=workunit.name,
                start_time=workunit.start_time,
            )

        self._apply_workunit_attributes(workunit=workunit, otel_span=otel_span)

        # Set the metrics for the session as an attribute of the root span.
        if not workunit.primary_parent_id:
            metrics = context.get_metrics()
            otel_span.set_attribute(
                "pantsbuild.metrics-v0", json.dumps(metrics, sort_keys=True, cls=_Encoder)
            )

        otel_span.end(end_time=_datetime_to_otel_timestamp(workunit.end_time))

        del self._otel_spans[otel_span_id]
        self._span_count += 1

    def finish(
        self, timeout: datetime.timedelta | None = None, *, context: ProcessorContext
    ) -> None:
        logger.debug("OpenTelemetryProcessor requested to finish workunit transmission.")
        logger.debug(f"OpenTelemetry processing counters: {self._counters.items()}")
        if len(self._otel_spans) > 0:
            logger.warning(
                "Multiple OpenTelemetry spans have not been submitted as completed to the library."
            )
        timeout_millis: int = int(timeout.total_seconds() * 1000.0) if timeout is not None else 2000
        self._span_processor.force_flush(timeout_millis)
        self._span_processor.shutdown()
