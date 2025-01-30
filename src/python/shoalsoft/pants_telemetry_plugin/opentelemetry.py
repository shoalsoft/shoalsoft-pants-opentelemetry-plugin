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
import typing
import uuid
from typing import TextIO

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider, sampling
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanProcessor, SpanExporter, SpanExportResult, SimpleSpanProcessor
from opentelemetry.sdk.trace.id_generator import IdGenerator, RandomIdGenerator
from opentelemetry.util import types

from shoalsoft.pants_telemetry_plugin.processor import IncompleteWorkunit, Processor, Workunit

_UNIX_EPOCH = datetime.datetime(year=1970, month=1, day=1, tzinfo=datetime.timezone.utc)


def _datetime_to_otel_timestamp(d: datetime.datetime) -> int:
    """OTEL times are nanoseconds since the Unix epoch."""
    duration_since_epoch = d - _UNIX_EPOCH
    nanoseconds = duration_since_epoch.days * 24 * 60 * 60 * 1000000
    nanoseconds += duration_since_epoch.seconds * 1000000
    nanoseconds += duration_since_epoch.microseconds * 1000
    return nanoseconds


class JsonFileSpanExporter(SpanExporter):
    def __init__(self, file: TextIO) -> None:
        self._file = file

    def export(
        self, spans: typing.Sequence[trace.ReadableSpan]
    ) -> SpanExportResult:
        for span in spans:
            self._file.write(span.to_json(indent=None) + "\n")
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        self._file.close()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        self._file.flush()


def get_otel_processor(otel_json_file_path: str) -> Processor:
    trace.set_tracer_provider(TracerProvider(sampler=sampling.ALWAYS_ON))
    tracer = trace.get_tracer(__name__)
    otel_json_file = open(otel_json_file_path, "w")
    span_exporter = JsonFileSpanExporter(otel_json_file)
    # span_processor = BatchSpanProcessor(span_exporter)
    span_processor = SimpleSpanProcessor(span_exporter)
    trace.get_tracer_provider().add_span_processor(span_processor)
    return OpenTelemetryProcessor(tracer, span_processor)


class DummySpan(trace.Span):
    """A dummy Span used in the thread context so we can trick OpenTelemetry as to what the parent span ID is."""

    def __init__(self, context: "trace.SpanContext") -> None:
        self._context = context

    def get_span_context(self) -> "trace.SpanContext":
        return self._context

    def is_recording(self) -> bool:
        return True

    def end(self, end_time: typing.Optional[int] = None) -> None:
        pass

    def set_attributes(
        self, attributes: typing.Dict[str, types.AttributeValue]
    ) -> None:
        pass

    def set_attribute(self, key: str, value: types.AttributeValue) -> None:
        pass

    def add_event(
        self,
        name: str,
        attributes: types.Attributes = None,
        timestamp: typing.Optional[int] = None,
    ) -> None:
        pass

    def add_link(
        self,
        context: trace.SpanContext,
        attributes: types.Attributes = None,
    ) -> None:
        pass

    def update_name(self, name: str) -> None:
        pass

    def set_status(
        self,
        status,  #: typing.Union[Status, StatusCode],
        description: typing.Optional[str] = None,
    ) -> None:
        pass

    def record_exception(
        self,
        exception: BaseException,
        attributes: types.Attributes = None,
        timestamp: typing.Optional[int] = None,
        escaped: bool = False,
    ) -> None:
        pass

    def __repr__(self) -> str:
        return f"DummySpan({self._context!r})"


class OpenTelemetryProcessor(Processor):
    def __init__(self, tracer: trace.Tracer, span_processor: SpanProcessor) -> None:
        self._tracer = tracer
        self._id_generator: IdGenerator = RandomIdGenerator()
        self._trace_id: int | None = None
        self._workunit_span_id_to_otel_span_id: dict[str, int] = {}
        self._otel_spans: dict[int, trace.Span] = {}
        self._span_processor = span_processor
        self._span_count: int = 0

    def start_workunit(self, workunit: IncompleteWorkunit) -> None:
        # Construct an OTEL `SpanContext` for the parent of this workunit (or else None for the root span).
        workunit_parent_span_id = workunit.primary_parent_id
        otel_context = trace.Context()
        if workunit_parent_span_id:
            # OpenTelemetry pulls the parent span ID from the span set as "current" in the context.
            assert self._trace_id is not None
            otel_parent_span_context = trace.SpanContext(
                trace_id=self._trace_id,
                span_id=self._workunit_span_id_to_otel_span_id[workunit_parent_span_id],
                is_remote=False,
            )
            otel_context = trace.set_span_in_context(DummySpan(otel_parent_span_context), context=otel_context)

        otel_span = self._tracer.start_span(
            name=workunit.name,
            context=otel_context,
            start_time=_datetime_to_otel_timestamp(workunit.start_time),
            record_exception=False,
            set_status_on_exception=False,
        )

        # TODO: Record any Pants-specific workunit attributes.
        
        # Record the span ID chosen by the tracer for this span.
        otel_span_context = otel_span.get_span_context()
        otel_span_id = otel_span_context.span_id
        self._workunit_span_id_to_otel_span_id[workunit.span_id] = otel_span_id
        self._otel_spans[otel_span_id] = otel_span

        # Record the trace ID the first time we make a span.
        if self._trace_id is None:
            self._trace_id = otel_span_context.trace_id

    def complete_workunit(self, workunit: Workunit) -> None:
        otel_span_id = self._workunit_span_id_to_otel_span_id[workunit.span_id]
        otel_span = self._otel_spans[otel_span_id]
        # TODO: Update the span with any changed attributes from the completed workunit.
        otel_span.end(end_time=_datetime_to_otel_timestamp(workunit.end_time))
        del self._otel_spans[otel_span_id]
        self._span_count += 1

    def finish(self) -> None:
        self._span_processor.shutdown()
        print(f"SPAN COUNT = {self._span_count}")
