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

import datetime
import logging
import typing
import urllib
from pathlib import Path
from typing import TextIO

from grpc import ChannelCredentials as GrpcChannelCredentials  # type: ignore[import-untyped]
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
from opentelemetry.trace.span import NonRecordingSpan, Span, SpanContext
from opentelemetry.trace.status import StatusCode

from shoalsoft.pants_telemetry_plugin.processor import (
    IncompleteWorkunit,
    Level,
    Processor,
    Workunit,
)
from shoalsoft.pants_telemetry_plugin.subsystem import (
    OtelCompression,
    TelemetrySubsystem,
    TracingExporterId,
)

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
    telemetry: TelemetrySubsystem,
) -> GrpcChannelCredentials:
    certificate_file = telemetry.otel_exporter_certificate_file
    if not certificate_file:
        return ssl_channel_credentials()
    client_key_file = telemetry.otel_exporter_client_key_file
    client_certificate_file = telemetry.otel_exporter_client_certificate_file

    root_certificates = (
        _read_file(certificate_file, "--shoalsoft-telemetry-otel-exporter-certificate-file")
        if certificate_file
        else None
    )
    private_key = (
        _read_file(client_key_file, "--shoalsoft-telemetry-otel-exporter-client-key-file")
        if client_key_file
        else None
    )
    certificate_chain = (
        _read_file(
            client_certificate_file,
            "--shoalsoft-telemetry-otel-exporter-client-certificate-file",
        )
        if client_certificate_file
        else None
    )

    return ssl_channel_credentials(
        root_certificates=root_certificates,
        private_key=private_key,
        certificate_chain=certificate_chain,
    )


def _make_span_exporter(name: TracingExporterId, telemetry: TelemetrySubsystem) -> SpanExporter:
    if name == TracingExporterId.OTLP_HTTP:
        return HttpOTLPSpanExporter(
            endpoint=telemetry.otel_exporter_endpoint,
            certificate_file=telemetry.otel_exporter_certificate_file,
            client_key_file=telemetry.otel_exporter_client_key_file,
            client_certificate_file=telemetry.otel_exporter_client_certificate_file,
            headers=telemetry.otel_exporter_headers,
            timeout=telemetry.otel_exporter_timeout,
            compression=Compression(telemetry.otel_exporter_compression.value),
        )
    elif name == TracingExporterId.OTLP_GRPC:
        compression = telemetry.otel_exporter_compression
        if compression not in _GRPC_COMPRESSION_MAP.keys():
            raise ValueError(
                f"OpenTelemetry compression mode `{compression.value}` is not supported for OTLP/gRPC exports."
            )

        credentials: GrpcChannelCredentials | None = None
        if not telemetry.otel_exporter_insecure:
            credentials = _get_grpc_credentials(telemetry)
        elif telemetry.otel_exporter_endpoint:
            parsed_endpoint = urllib.parse.urlparse(telemetry.otel_exporter_endpoint)
            if parsed_endpoint.scheme == "https":
                raise ValueError(
                    "`--shoalsoft-telemetry-otel-exporter-insecure` is enabled, but the endpoint "
                    f"`{telemetry.otel_exporter_endpoint}` contains a `https` scheme which "
                    "requires secure mode. Please set `--no-shoalsoft-telemetry-otel-exporter-insecure` "
                    "instead."
                )

        return GrpcOTLPSpanExporter(
            endpoint=telemetry.otel_exporter_endpoint,
            insecure=telemetry.otel_exporter_insecure,
            credentials=credentials,
            headers=telemetry.otel_exporter_headers,
            timeout=telemetry.otel_exporter_timeout,
            compression=_GRPC_COMPRESSION_MAP[compression],
        )
    else:
        raise AssertionError(f"Unknown OpenTelemetry tracing span exporter: {name}")


def get_otel_processor(
    span_exporter_name: TracingExporterId,
    telemetry: TelemetrySubsystem,
    build_root: Path,
) -> Processor:
    resource = Resource(
        attributes={
            SERVICE_NAME: "pantsbuild",
        }
    )
    trace.set_tracer_provider(TracerProvider(sampler=sampling.ALWAYS_ON, resource=resource))
    tracer = trace.get_tracer(__name__)

    span_exporter: SpanExporter
    if span_exporter_name == TracingExporterId.OTEL_JSON_FILE:
        otel_json_file_path_str = telemetry.otel_json_file
        if not otel_json_file_path_str:
            raise ValueError(
                f"`--shoalsoft-telemetry-exporters` includes `{TracingExporterId.OTEL_JSON_FILE}` "
                "but the `--shoalsoft-telemetry-otel-json-file` option is not set."
            )
        otel_json_file_path = build_root / otel_json_file_path_str
        otel_json_file_path.parent.mkdir(parents=True, exist_ok=True)
        span_exporter = JsonFileSpanExporter(open(otel_json_file_path, "w"))
        logger.debug(f"Enabling OpenTelemetry JSON file span exporter: path={otel_json_file_path}")
    elif span_exporter_name in {TracingExporterId.OTLP_HTTP, TracingExporterId.OTLP_GRPC}:
        span_exporter = _make_span_exporter(span_exporter_name, telemetry=telemetry)
        logger.debug(f"Enabling OpenTelemetry span exporter `{span_exporter_name.value}`.")
    else:
        raise AssertionError(
            f"Asked to construct an unknown span exporter: {span_exporter_name.value}"
        )

    span_processor = BatchSpanProcessor(span_exporter)
    trace.get_tracer_provider().add_span_processor(span_processor)  # type: ignore[attr-defined]

    return OpenTelemetryProcessor(tracer, span_processor)


class DummySpan(NonRecordingSpan):
    """A dummy Span used in the thread context so we can trick OpenTelemetry as
    to what the parent span ID is.

    Sets `is_recording` to True.
    """

    def is_recording(self) -> bool:
        return True

    def __repr__(self) -> str:
        return f"DummySpan({self._context!r})"


class OpenTelemetryProcessor(Processor):
    def __init__(self, tracer: trace.Tracer, span_processor: SpanProcessor) -> None:
        self._tracer = tracer
        self._trace_id: int | None = None
        self._workunit_span_id_to_otel_span_id: dict[str, int] = {}
        self._otel_spans: dict[int, trace.Span] = {}
        self._span_processor = span_processor
        self._span_count: int = 0
        self._counters: dict[str, int] = {}

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

        otel_span = self._tracer.start_span(
            name=name,
            context=otel_context,
            start_time=_datetime_to_otel_timestamp(start_time),
            record_exception=False,
            set_status_on_exception=False,
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

    def start_workunit(self, workunit: IncompleteWorkunit) -> None:
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

    def complete_workunit(self, workunit: Workunit) -> None:
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

        otel_span.end(end_time=_datetime_to_otel_timestamp(workunit.end_time))

        del self._otel_spans[otel_span_id]
        self._span_count += 1

    def finish(self) -> None:
        logger.debug("OpenTelemetryProcessor requested to finish workunit transmission.")
        logger.debug(f"OpenTelemetry processing counters: {self._counters.items()}")
        self._span_processor.shutdown()
