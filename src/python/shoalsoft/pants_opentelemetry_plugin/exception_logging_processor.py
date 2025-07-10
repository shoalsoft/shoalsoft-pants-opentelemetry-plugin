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
from contextlib import contextmanager
from typing import Generator

from shoalsoft.pants_opentelemetry_plugin.processor import (
    IncompleteWorkunit,
    Processor,
    ProcessorContext,
    Workunit,
)

logger = logging.getLogger(__name__)


class ExceptionLoggingProcessor(Processor):
    def __init__(self, processor: Processor, *, name: str) -> None:
        self._processor = processor
        self._name = name
        self._exception_count = 0

    @contextmanager
    def _wrapper(self) -> Generator[None, None, None]:
        try:
            yield
        except Exception as ex:
            logger.debug(
                f"An exception occurred while processing a workunit in the {self._name} workunit tracing handler: {ex}",
                exc_info=True,
            )
            if self._exception_count == 0:
                logger.warning(
                    f"Ignored an exception from the {self._name} workunit tracing handler. These exceptions will be logged "
                    "at DEBUG level. No further warnings will be logged."
                )
            self._exception_count += 1

    def initialize(self) -> None:
        with self._wrapper():
            self._processor.initialize()

    def start_workunit(self, workunit: IncompleteWorkunit, *, context: ProcessorContext) -> None:
        with self._wrapper():
            self._processor.start_workunit(workunit=workunit, context=context)

    def complete_workunit(self, workunit: Workunit, *, context: ProcessorContext) -> None:
        with self._wrapper():
            self._processor.complete_workunit(workunit=workunit, context=context)

    def finish(
        self, timeout: datetime.timedelta | None = None, *, context: ProcessorContext
    ) -> None:
        with self._wrapper():
            self._processor.finish(timeout=timeout, context=context)
        if self._exception_count > 1:
            logger.warning(
                f"Ignored {self._exception_count} exceptions from the {self._name} workunit tracing handler."
            )
