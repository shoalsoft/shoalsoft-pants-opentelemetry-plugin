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

from pants.option.option_types import BoolOption, DictOption, EnumOption, IntOption, StrOption
from pants.option.subsystem import Subsystem
from pants.util.strutil import softwrap


class TracingExporterId(enum.Enum):
    HTTP = "http"
    GRPC = "grpc"
    JSON_FILE = "json-file"


class OtelCompression(enum.Enum):
    GZIP = "gzip"
    DEFLATE = "deflate"
    NONE = "none"


class TelemetrySubsystem(Subsystem):
    options_scope = "shoalsoft-opentelemetry"
    help = "Pants OpenTelemetry plugin from Shoal Software LLC"

    enabled = BoolOption(default=False, help="Whether to enable emitting OpenTelemetry spans.")

    exporter = EnumOption(
        default=TracingExporterId.JSON_FILE,
        help=softwrap(
            f"""
            Set the exporter to use when exporting workunits to external tracing systems. Choices are
            `{TracingExporterId.HTTP.value}` (OpenTelemetry OTLP HTTP),
            `{TracingExporterId.GRPC.value}` (OpenTelemetry OTLP GRPC), and
            `{TracingExporterId.JSON_FILE.value}` (OpenTelemetry debug output to a file).
            Default is `{TracingExporterId.JSON_FILE.value}`.
            """
        ),
    )

    parent_trace_id = StrOption(
        default="",
        help=softwrap(
            """
            The parent trace ID to use for the generated trace. This is useful for linking traces together
            in a distributed system. The trace ID should be a 16-byte hex string.
            """
        ),
    )

    json_file = StrOption(
        default="dist/otel-json-trace.jsonl",
        help=softwrap(
            f"""
            If set, Pants will write OpenTelemetry tracing spans to a local file for easier debugging. Each line
            will be a tracing span in OpenTelemetry's JSON format. The filename is relative to the build root. Export
            will only occur if the `--shoalsoft-opentelemetry-exporter` is set to `{TracingExporterId.JSON_FILE.value}`.
            """
        ),
    )

    exporter_endpoint = StrOption(
        default=None,
        help=softwrap(
            f"""
            The target to which the span exporter is going to send spans. The endpoint MUST be a valid URL host,
            and MAY contain a scheme (http or https), port and path. A scheme of https indicates a secure
            connection and takes precedence over this configuration setting. Endpoint which will receive exported
            tracing spans.

            This option is consumed by both the `{TracingExporterId.HTTP.value}` and `{TracingExporterId.GRPC.value}`
            exporters.

            Corresponds to the `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` and `OTEL_EXPORTER_OTLP_ENDPOINT`
            environment variables.
            """
        ),
    )

    exporter_certificate_file = StrOption(
        default=None,
        advanced=True,
        help=softwrap(
            """
            The path to the certificate file for TLS credentials of gRPC client for traces.
            Should only be used for a secure connection for tracing.

            Corresponds to the `OTEL_EXPORTER_OTLP_TRACES_CLIENT_KEY` and `OTEL_EXPORTER_OTLP_CERTIFICATE`
            environment variables.
            """
        ),
    )

    exporter_client_key_file = StrOption(
        default=None,
        advanced=True,
        help=softwrap(
            """
            The path to the client private key to use in mTLS communication in PEM format for traces.

            Corresponds to the `OTEL_EXPORTER_OTLP_TRACES_CLIENT_KEY` and `OTEL_EXPORTER_OTLP_CLIENT_KEY`
            environment variables.
            """
        ),
    )

    exporter_client_certificate_file = StrOption(
        default=None,
        advanced=True,
        help=softwrap(
            """
            The path to the client certificate/chain trust for clients private key to use in mTLS
            communication in PEM format for traces.

            Corresponds to the `OTEL_EXPORTER_OTLP_TRACES_CLIENT_CERTIFICATE` and
            `OTEL_EXPORTER_OTLP_CLIENT_CERTIFICATE` environment variables.
            """
        ),
    )

    exporter_headers = DictOption[str](
        advanced=True,
        help=softwrap(
            """
            The key-value pairs to be used as headers for spans associated with gRPC or HTTP requests.

            This option is consumed by both the `{TracingExporterId.HTTP.value}` and `{TracingExporterId.GRPC.value}`
            exporters.

            Corresponds to the `OTEL_EXPORTER_OTLP_TRACES_HEADERS` and `OTEL_EXPORTER_OTLP_HEADERS`
            environment variables.
            """
        ),
    )

    exporter_timeout = IntOption(
        default=None,
        advanced=True,
        help=softwrap(
            f"""
            The maximum time the OTLP exporter will wait for each batch export for spans.

            This option is consumed by both the `{TracingExporterId.HTTP.value}` and `{TracingExporterId.GRPC.value}`
            exporters.

            Corresponds to the `OTEL_EXPORTER_OTLP_TRACES_TIMEOUT` and `OTEL_EXPORTER_OTLP_TIMEOUT`
            environment variables.
            """
        ),
    )

    exporter_compression = EnumOption(
        default=OtelCompression.NONE,
        advanced=True,
        help=softwrap(
            f"""
            Specifies a gRPC compression method to be used in the OTLP exporters. Possible values are `gzip`,
            `deflate`, and `none`.

            This option is consumed by both the `{TracingExporterId.HTTP.value}` and `{TracingExporterId.GRPC.value}`
            exporters.

            Corresponds to the `OTEL_EXPORTER_OTLP_TRACES_COMPRESSION` and `OTEL_EXPORTER_OTLP_COMPRESSION`
            environment variables.
            """
        ),
    )

    exporter_insecure = BoolOption(
        default=None,
        advanced=True,
        help=softwrap(
            f"""
            Represents whether to enable client transport security for gRPC requests. An endpoint scheme of https
            will error if this option is in effect since `https` implies secure mode.

            This option is consumed by the `{TracingExporterId.GRPC.value}` exporter.

            Corresponds to the `OTEL_EXPORTER_OTLP_TRACES_INSECURE` and `OTEL_EXPORTER_OTLP_INSECURE`
            environment variables.
            """
        ),
    )
