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

import argparse
import enum
import json
from collections.abc import Mapping
from dataclasses import dataclass

from pants.util.frozendict import FrozenDict
from shoalsoft.pants_opentelemetry_plugin.processor import IncompleteWorkunit, Workunit


class ProcessorOperation(enum.Enum):
    INITIALIZE = "initialize"
    START_WORKUNIT = "start_workunit"
    COMPLETE_WORKUNIT = "complete_workunit"
    FINISH = "finish"
    SHUTDOWN = "shutdown"


@dataclass(frozen=True)
class OtelParameters:
    endpoint: str | None
    certificate_file: str | None
    client_key_file: str | None
    client_certificate_file: str | None
    headers: Mapping[str, str] | None
    timeout: int | None
    compression: str | None
    insecure: bool | None

    def to_args_for_subprocess(self) -> list[str]:
        args = []
        if self.endpoint is not None:
            args.extend(["--endpoint", self.endpoint])
        if self.certificate_file is not None:
            args.extend(["--certificate_file", self.certificate_file])
        if self.client_key_file is not None:
            args.extend(["--client_key_file", self.client_key_file])
        if self.client_certificate_file is not None:
            args.extend(["--client_certificate_file", self.client_certificate_file])
        if self.headers is not None:
            args.extend(["--headers", json.dumps(self.headers)])
        if self.timeout is not None:
            args.extend(["--timeout", str(self.timeout)])
        if self.compression is not None:
            args.extend(["--compression", self.compression])
        if self.insecure is not None:
            args.append("--insecure" if self.insecure else "--no-insecure")
        return args

    @classmethod
    def from_parsed_options(cls, options: argparse.Namespace) -> OtelParameters:
        return cls(
            endpoint=options.endpoint if options.endpoint is not None else None,
            certificate_file=(
                options.certificate_file if options.certificate_file is not None else None
            ),
            client_key_file=(
                options.client_key_file if options.client_key_file is not None else None
            ),
            client_certificate_file=(
                options.client_certificate_file
                if options.client_certificate_file is not None
                else None
            ),
            headers=json.loads(options.headers) if options.headers is not None else None,
            timeout=options.timeout if options.timeout is not None else None,
            compression=options.compression if options.compression is not None else None,
            insecure=options.insecure if hasattr(options, "insecure") else None,
        )

    @staticmethod
    def add_options_to_parser(parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--endpoint", default=None, action="store")
        parser.add_argument("--certificate_file", default=None, action="store")
        parser.add_argument("--client_key_file", default=None, action="store")
        parser.add_argument("--client_certificate_file", default=None, action="store")
        parser.add_argument("--headers", default=None, action="store")
        parser.add_argument("--timeout", default=None, type=int, action="store")
        parser.add_argument("--compression", default=None, action="store")
        insecure_group = parser.add_mutually_exclusive_group()
        insecure_group.add_argument("--insecure", dest="insecure", action="store_true")
        insecure_group.add_argument("--no-insecure", dest="insecure", action="store_false")
        parser.set_defaults(insecure=False)


@dataclass(frozen=True)
class InitializeData:
    otel_parameters: OtelParameters
    build_root: str
    traceparent_env_var: str | None


@dataclass(frozen=True)
class StartWorkunitData:
    workunit: IncompleteWorkunit
    context_metrics: FrozenDict[str, int]


@dataclass(frozen=True)
class CompleteWorkunitData:
    workunit: Workunit
    context_metrics: FrozenDict[str, int]


@dataclass(frozen=True)
class FinishData:
    timeout_seconds: float | None
    context_metrics: FrozenDict[str, int]


ProcessorMessageDataT = InitializeData | StartWorkunitData | CompleteWorkunitData | FinishData


@dataclass(frozen=True)
class ProcessorMessage:
    operation: ProcessorOperation
    data: ProcessorMessageDataT
    sequence_id: int
