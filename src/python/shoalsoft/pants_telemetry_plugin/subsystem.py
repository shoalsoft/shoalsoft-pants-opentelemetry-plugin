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

import enum

from pants.option.option_types import BoolOption, EnumListOption, StrOption
from pants.option.subsystem import Subsystem
from pants.util.strutil import softwrap


class TracingExporterId(enum.Enum):
    OTLP_HTTP = "otlp-http"
    OTLP_GRPC = "otlp-grpc"
    OTEL_JSON_FILE = "otel-json-file"


class TelemetrySubsystem(Subsystem):
    options_scope = "shoalsoft-telemetry"
    help = "Pants Telemetry plugin from Shoal Software"

    enabled = BoolOption("--enabled", default=False, help="Whether to enable telemetry.")

    exporters = EnumListOption(
        enum_type=TracingExporterId,
        default=[],
        help=softwrap(
            f"""
            Set the exporters to use when exporting workunits to external tracing systems. Choices are
            `{TracingExporterId.OTLP_HTTP}` (OpenTelemetry OTLP HTTP),
            `{TracingExporterId.OTLP_GRPC}` (OpenTelemetry OTLP GRPC), and
            `{TracingExporterId.OTEL_JSON_FILE}` (OpenTelemetry debug output to a file).
            Default is not export spans at all.

            Configure each OpenTelemetry exporter using the applicable OpenTelemetry environment variables.
            TODO: Add link to OTEL docs for those environment variables here.
            """
        ),
    )

    otel_json_file = StrOption(
        default="dist/otel-json-trace.jsonl",
        help=softwrap(
            f"""
            If set, Pants will write OpenTelemetry tracing spans to a local file for easier debugging. Each line
            will be a tracing span in OpenTelemetry's JSON format. The filename is relative to the build root. Export
            will only occur if the `--shoalsoft-telemetry-exporters` option includes `{TracingExporterId.OTEL_JSON_FILE}`.
            """
        ),
    )
