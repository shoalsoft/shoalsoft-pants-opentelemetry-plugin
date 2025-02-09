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
from typing import Any, Mapping

from pants.engine.internals.native_engine import all_counter_names
from pants.engine.internals.scheduler import Workunit as RawWorkunit
from pants.engine.streaming_workunit_handler import StreamingWorkunitContext, WorkunitsCallback
from pants.util.frozendict import FrozenDict
from shoalsoft.pants_telemetry_plugin.processor import (
    IncompleteWorkunit,
    Level,
    Processor,
    ProcessorContext,
    Workunit,
)


class _TelemetryContext(ProcessorContext):
    def __init__(self, pants_context: StreamingWorkunitContext) -> None:
        self._pants_context = pants_context

    def get_metrics(self) -> Mapping[str, int]:
        metric_names = all_counter_names()
        metrics = self._pants_context.get_metrics()
        for metric_name in metric_names:
            if metric_name not in metrics:
                metrics[metric_name] = 0
        return metrics


class TelemetryWorkunitsCallback(WorkunitsCallback):
    def __init__(self, processor: Processor) -> None:
        self.processor: Processor = processor

    @property
    def can_finish_async(self) -> bool:
        return False

    def _convert_time(self, seconds: int, nanoseconds: int) -> datetime.datetime:
        t = datetime.datetime(year=1970, month=1, day=1, tzinfo=datetime.timezone.utc)
        t = t + datetime.timedelta(seconds=seconds, microseconds=nanoseconds // 1000)
        return t

    def _convert_incomplete_workunit(self, raw_workunit: RawWorkunit) -> IncompleteWorkunit:
        return IncompleteWorkunit(
            name=raw_workunit["name"],
            span_id=raw_workunit["span_id"],
            parent_ids=tuple(raw_workunit["parent_ids"]),
            level=Level(raw_workunit["level"]),
            description=raw_workunit.get("description"),
            start_time=self._convert_time(raw_workunit["start_secs"], raw_workunit["start_nanos"]),
        )

    def _convert_completed_workunit(self, raw_workunit: RawWorkunit) -> Workunit:
        start_time = self._convert_time(raw_workunit["start_secs"], raw_workunit["start_nanos"])
        end_time = start_time + datetime.timedelta(
            seconds=raw_workunit["duration_secs"],
            microseconds=raw_workunit["duration_nanos"] // 1000,
        )
        return Workunit(
            name=raw_workunit["name"],
            span_id=raw_workunit["span_id"],
            parent_ids=tuple(raw_workunit["parent_ids"]),
            level=Level(raw_workunit["level"]),
            description=raw_workunit.get("description"),
            start_time=start_time,
            end_time=end_time,
            metadata=FrozenDict.deep_freeze(raw_workunit.get("metadata", {})),
        )

    def __call__(
        self,
        *,
        completed_workunits: tuple[RawWorkunit, ...],
        started_workunits: tuple[RawWorkunit, ...],
        context: StreamingWorkunitContext,
        finished: bool = False,
        **kwargs: Any,
    ) -> None:
        telemetry_context = _TelemetryContext(context)

        for started_workunit in started_workunits:
            self.processor.start_workunit(
                self._convert_incomplete_workunit(started_workunit), context=telemetry_context
            )

        for completed_workunit in completed_workunits:
            self.processor.complete_workunit(
                self._convert_completed_workunit(completed_workunit), context=telemetry_context
            )

        if finished:
            self.processor.finish(context=telemetry_context)
