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

import urllib.parse
from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class OtlpParameters:
    endpoint: str | None
    traces_endpoint: str | None
    certificate_file: str | None
    client_key_file: str | None
    client_certificate_file: str | None
    headers: Mapping[str, str] | None
    timeout: int | None
    compression: str | None

    def resolve_traces_endpoint(self) -> str:
        if self.traces_endpoint:
            return self.traces_endpoint

        if not self.endpoint:
            return "http://localhost:4317"

        url = urllib.parse.urlparse(self.endpoint)
        scheme = url.scheme if url.scheme else "http"
        path = url.path
        if not path.endswith("/"):
            path = path + "/"
        path = f"{path}/v1/traces"
        url = url._replace(scheme=scheme, path=path)
        return url.geturl()
