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
import enum
from dataclasses import dataclass
from typing import Any, Protocol

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


class Processor(Protocol):
    """Protocol for emitter implementations."""

    def start_workunit(self, workunit: IncompleteWorkunit) -> None:
        ...

    def complete_workunit(self, workunit: Workunit) -> None:
        ...

    def finish(self) -> None:
        ...
