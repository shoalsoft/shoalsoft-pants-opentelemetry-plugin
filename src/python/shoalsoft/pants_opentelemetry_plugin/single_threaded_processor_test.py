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
import queue
from collections.abc import Mapping

from pants.util.frozendict import FrozenDict
from shoalsoft.pants_opentelemetry_plugin.processor import (
    IncompleteWorkunit,
    Level,
    Processor,
    ProcessorContext,
    Workunit,
)
from shoalsoft.pants_opentelemetry_plugin.single_threaded_processor import SingleThreadedProcessor


class CapturingProcessor(Processor):
    def __init__(self) -> None:
        self.initialize_called = False
        self.started_workunits: queue.Queue[IncompleteWorkunit] = queue.Queue()
        self.completed_workunits: queue.Queue[Workunit] = queue.Queue()
        self.finish_called = False

    def initialize(self) -> None:
        self.initialize_called = True

    def start_workunit(self, workunit: IncompleteWorkunit, *, context: ProcessorContext) -> None:
        self.started_workunits.put_nowait(workunit)

    def complete_workunit(self, workunit: Workunit, *, context: ProcessorContext) -> None:
        self.completed_workunits.put_nowait(workunit)

    def finish(
        self, timeout: datetime.timedelta | None = None, *, context: ProcessorContext
    ) -> None:
        self.finish_called = True


class MockProcessorContext(ProcessorContext):
    def get_metrics(self) -> Mapping[str, int]:
        return {}


def test_single_threaded_processor_roundtrip() -> None:
    context = MockProcessorContext()
    processor = CapturingProcessor()
    stp_processor = SingleThreadedProcessor(processor)

    stp_processor.initialize()
    assert processor.initialize_called

    start_time = datetime.datetime.now(datetime.timezone.utc)
    incomplete_workunit = IncompleteWorkunit(
        name="test-span",
        span_id="SOME_SPAN_ID",
        parent_ids=("A_PARENT_SPAN_ID",),
        level=Level.INFO,
        description="This is where the span is described.",
        start_time=start_time,
    )
    stp_processor.start_workunit(workunit=incomplete_workunit, context=context)
    actual_incomplete_workunit = processor.started_workunits.get(timeout=0.250)
    assert actual_incomplete_workunit == incomplete_workunit

    start_time = datetime.datetime.now(datetime.timezone.utc)
    workunit = Workunit(
        name=incomplete_workunit.name,
        span_id=incomplete_workunit.span_id,
        parent_ids=incomplete_workunit.parent_ids,
        level=incomplete_workunit.level,
        description=incomplete_workunit.description,
        start_time=incomplete_workunit.start_time,
        end_time=incomplete_workunit.start_time + datetime.timedelta(milliseconds=100),
        metadata=FrozenDict(),
    )
    stp_processor.complete_workunit(workunit=workunit, context=context)
    actual_workunit = processor.completed_workunits.get(timeout=0.250)
    assert actual_workunit == workunit

    stp_processor.finish(context=context)
    assert processor.finish_called
