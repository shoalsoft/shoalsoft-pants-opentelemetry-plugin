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

import queue
import time
from enum import Enum
from threading import Event, Lock, Thread

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
    """This is a `Processor` implementation which pushes all received workunits
    onto a queeue for processing on a single thread.

    This is useful to prevent race conditions with the fact that the
    Pants workunits systenm can invoke a streaming workunit handler on
    multiple threads.
    """

    def __init__(self, processor: Processor) -> None:
        self._processor = processor

        self._initialize_completed_event = Event()
        self._finish_completed_event = Event()

        self._queue_lock = Lock()
        self._queue: queue.Queue[
            tuple[_MessageType, Workunit | IncompleteWorkunit | None, ProcessorContext]
        ] = queue.Queue()

        self._thread = Thread(target=self._processing_loop)
        self._thread.daemon = True

    def _handle_message(
        self, msg: tuple[_MessageType, Workunit | IncompleteWorkunit | None, ProcessorContext]
    ) -> ProcessorContext | None:
        """Processes messages.

        Returns a `ProcessorContext` to use for shutdown if finish was
        triggered.
        """
        msg_type: _MessageType = msg[0]
        if msg_type == _MessageType.START_WORKUNIT:
            incomplete_workunit = msg[1]
            assert isinstance(incomplete_workunit, IncompleteWorkunit)
            self._processor.start_workunit(workunit=incomplete_workunit, context=msg[2])
            return None
        elif msg_type == _MessageType.COMPLETE_WORKUNIT:
            workunit = msg[1]
            assert isinstance(workunit, Workunit)
            self._processor.complete_workunit(workunit=workunit, context=msg[2])
            return None
        elif msg_type == _MessageType.FINISH:
            # Finish signalled. Let caller know what context to use for it.
            return msg[2]
        else:
            raise AssertionError("Received unknown message type in SingleThreadedProcessor.")

    def _processing_loop(self) -> None:
        self._processor.initialize()
        self._initialize_completed_event.set()

        finish_context: ProcessorContext | None
        while msg := self._queue.get():
            finish_context = self._handle_message(msg)
            if finish_context:
                break

        # Once "finish" has been signalled, we set a deadline and continue processing workunit messages
        # until the deadline is reached.
        deadline = time.time() + 0.25
        try:
            while msg := self._queue.get(timeout=deadline - time.time()):
                _ = self._handle_message(msg)
        except queue.Empty:
            pass

        self._processor.finish(context=finish_context)
        self._finish_completed_event.set()

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
