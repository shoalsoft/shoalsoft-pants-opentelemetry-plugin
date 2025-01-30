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

python_sources()

python_tests(
    name="tests",
    overrides={
        "opentelemetry_integration_test.py": {
            "dependencies": ["//src/python:plugin_files_for_integration_test"]
        }
    },
)

pants_requirements(name="pants-reqs")
