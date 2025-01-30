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

from pants.option.option_types import BoolOption, StrOption
from pants.option.subsystem import Subsystem


class TelemetrySubsystem(Subsystem):
    options_scope = "shoalsoft-telemetry"
    help = "Pants Telemetry plugin from Shoal Software"

    enabled = BoolOption("--enabled", default=False, help="Whether to enable telemetry.")

    otel_json_file = StrOption(
        default="dist/otel-trace.jsonl",
        help="Where to write the OTEL JSON workunits to.",
    )
