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

import json
from pathlib import Path
from typing import Any, TextIO

from pants.engine.fs import FileDigest, Snapshot
from pants.engine.internals.scheduler import Workunit
from pants.engine.streaming_workunit_handler import StreamingWorkunitContext, WorkunitsCallback


# TODO: This is a placeholder handler intended to just dump workunits to disk while this plugin is
# being developed.
class TelemetryWorkunitsCallback(WorkunitsCallback):
    def __init__(self, filename: str):
        base_path = Path(filename)
        self.start_file_path = base_path.with_name(f"{base_path.name}-started")
        self.start_file_path.parent.mkdir(parents=True, exist_ok=True)
        self.start_file: TextIO | None = open(self.start_file_path, "w")
        self.completed_file_path = base_path.with_name(f"{base_path.name}-completed")
        self.completed_file_path.parent.mkdir(parents=True, exist_ok=True)
        self.completed_file: TextIO | None = open(self.completed_file_path, "w")

    @property
    def can_finish_async(self) -> bool:
        return False

    @staticmethod
    def workunit_to_json(workunit: Workunit) -> dict[str, Any]:
        def convert(v: Any) -> Any:
            if isinstance(v, (FileDigest, Snapshot)):
                return repr(v)
            return v

        return {key: convert(value) for key, value in workunit.items()}

    def __call__(
        self,
        *,
        completed_workunits: tuple[Workunit, ...],
        started_workunits: tuple[Workunit, ...],
        context: StreamingWorkunitContext,
        finished: bool = False,
        **kwargs: Any,
    ) -> None:
        if self.start_file:
            for workunit in started_workunits:
                self.start_file.write(json.dumps(self.workunit_to_json(workunit)) + "\n")
            if finished:
                self.start_file.close()
                self.start_file = None
        if self.completed_file:
            for workunit in completed_workunits:
                self.completed_file.write(json.dumps(self.workunit_to_json(workunit)) + "\n")
            if finished:
                self.completed_file.write(json.dumps(context.get_metrics()) + "\n")
                self.completed_file.close()
                self.completed_file = None
