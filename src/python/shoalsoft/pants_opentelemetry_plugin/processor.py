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
import enum
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from pants.util.frozendict import FrozenDict


class Level(enum.Enum):
    DEBUG = "DEBUG"
    ERROR = "ERROR"
    INFO = "INFO"
    TRACE = "TRACE"
    WARN = "WARN"


@dataclass(frozen=True)
class IncompleteWorkunit:
    """An incomplete workunit which only knows its start time."""

    name: str
    span_id: str
    parent_ids: tuple[str, ...]
    level: Level
    description: str | None
    start_time: datetime.datetime

    @property
    def primary_parent_id(self) -> str | None:
        if len(self.parent_ids) > 0:
            return self.parent_ids[0]
        return None


@dataclass(frozen=True)
class Workunit(IncompleteWorkunit):
    """The final workunit which knows when it completed as well."""

    end_time: datetime.datetime
    metadata: FrozenDict[str, Any]


class ProcessorContext(Protocol):
    def get_metrics(self) -> Mapping[str, int]: ...


class Processor(Protocol):
    """Protocol for emitter implementations."""

    def initialize(self) -> None: ...

    def start_workunit(
        self, workunit: IncompleteWorkunit, *, context: ProcessorContext
    ) -> None: ...

    def complete_workunit(self, workunit: Workunit, *, context: ProcessorContext) -> None: ...

    def finish(
        self, timeout: datetime.timedelta | None = None, *, context: ProcessorContext
    ) -> None: ...
