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

from pants.engine.rules import collect_rules, rule
from pants.engine.streaming_workunit_handler import (
    WorkunitsCallbackFactory,
    WorkunitsCallbackFactoryRequest,
)
from pants.engine.unions import UnionRule
from shoalsoft.pants_telemetry_plugin.subsystem import TelemetrySubsystem
from shoalsoft.pants_telemetry_plugin.workunits import TelemetryWorkunitsCallback


class TelemetryWorkunitsCallbackFactoryRequest(WorkunitsCallbackFactoryRequest):
    pass


@rule
async def telemetry_workunits_callback_factory_request(
    _: TelemetryWorkunitsCallbackFactoryRequest, telemetry: TelemetrySubsystem
) -> WorkunitsCallbackFactory:
    return WorkunitsCallbackFactory(
        lambda: TelemetryWorkunitsCallback(telemetry.workunits_file) if telemetry.enabled else None
    )


def rules():
    return (
        *collect_rules(),
        UnionRule(WorkunitsCallbackFactoryRequest, TelemetryWorkunitsCallbackFactoryRequest),
    )
