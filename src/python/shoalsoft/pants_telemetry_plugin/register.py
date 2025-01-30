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

import logging
from pants.base.build_root import BuildRoot
from pants.engine.internals.session import RunId
from pants.engine.rules import collect_rules, rule
from pants.engine.streaming_workunit_handler import (
    WorkunitsCallbackFactory,
    WorkunitsCallbackFactoryRequest,
)
from pants.engine.unions import UnionRule
from shoalsoft.pants_telemetry_plugin.opentelemetry import get_otel_processor
from shoalsoft.pants_telemetry_plugin.processor import Processor
from shoalsoft.pants_telemetry_plugin.stream_handler import TelemetryWorkunitsCallback
from shoalsoft.pants_telemetry_plugin.subsystem import TelemetrySubsystem


logger = logging.getLogger(__name__)

class TelemetryWorkunitsCallbackFactoryRequest(WorkunitsCallbackFactoryRequest):
    pass


@rule
async def telemetry_workunits_callback_factory_request(
    _: TelemetryWorkunitsCallbackFactoryRequest, telemetry: TelemetrySubsystem, build_root: BuildRoot, run_id: RunId
) -> WorkunitsCallbackFactory:
    processor: Processor | None = None
    if telemetry.enabled and telemetry.otel_json_file:
        otel_json_file_path = build_root.pathlib_path / telemetry.otel_json_file
        # otel_json_file_path = otel_json_file_path.with_name(f"{otel_json_file_path.name}-{run_id}")
        otel_json_file_path.parent.mkdir(parents=True, exist_ok=True)
        processor = get_otel_processor(str(otel_json_file_path))
        logger.debug(f"Enabling OpenTelemetry file processor: path={otel_json_file_path}")
    return WorkunitsCallbackFactory(
        lambda: TelemetryWorkunitsCallback(processor) if processor is not None else None
    )


def rules():
    return (
        *collect_rules(),
        UnionRule(WorkunitsCallbackFactoryRequest, TelemetryWorkunitsCallbackFactoryRequest),
    )
