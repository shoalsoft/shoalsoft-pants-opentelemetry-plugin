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

from enum import Enum
from queue import Queue
from threading import Event, Thread

from shoalsoft.pants_opentelemetry_plugin.processor import (
    IncompleteWorkunit,
    Processor,
    ProcessorContext,
    Workunit,
)


class _MessageType(Enum):
    START_WORKUNIT = "start_workunit"
    COMPLETE_WORKUNIT = "complete_workunit"
    FINISH = "finish"


class SingleThreadedProcessor(Processor):
    def __init__(self, inner: Processor) -> None:
        self._inner = inner
        self._initialize_completed_event = Event()
        self._finish_completed_event = Event()
        self._queue: Queue[
            tuple[_MessageType, Workunit | IncompleteWorkunit | None, ProcessorContext]
        ] = Queue()
        self._thread = Thread(target=self._start_processor)
        self._thread.daemon = True

    def _start_processor(self) -> None:
        self._inner.initialize()
        self._initialize_completed_event.set()

        while msg := self._queue.get():
            msg_type: _MessageType = msg[0]
            if msg_type == _MessageType.START_WORKUNIT:
                incomplete_workunit = msg[1]
                assert incomplete_workunit is not None and isinstance(
                    incomplete_workunit, IncompleteWorkunit
                )
                self._inner.start_workunit(workunit=incomplete_workunit, context=msg[2])
            elif msg_type == _MessageType.COMPLETE_WORKUNIT:
                workunit = msg[1]
                assert workunit is not None and isinstance(workunit, Workunit)
                self._inner.complete_workunit(workunit=workunit, context=msg[2])
            elif msg_type == _MessageType.FINISH:
                assert msg[1] is None
                self._inner.finish(context=msg[2])
                self._finish_completed_event.set()
                break

    def initialize(self) -> None:
        self._thread.start()
        self._initialize_completed_event.wait()

    def start_workunit(self, workunit: IncompleteWorkunit, *, context: ProcessorContext) -> None:
        self._queue.put_nowait((_MessageType.START_WORKUNIT, workunit, context))

    def complete_workunit(self, workunit: Workunit, *, context: ProcessorContext) -> None:
        self._queue.put_nowait((_MessageType.COMPLETE_WORKUNIT, workunit, context))

    def finish(self, *, context: ProcessorContext) -> None:
        self._queue.put_nowait((_MessageType.FINISH, None, context))
        self._finish_completed_event.wait()
        self._thread.join()
