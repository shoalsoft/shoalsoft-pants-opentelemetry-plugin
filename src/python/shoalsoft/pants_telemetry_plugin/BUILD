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
            "runtime_package_dependencies": [
                ":wheel-2.24.x",
                ":wheel-2.23.x",
                ":pants-for-tests@parametrize=pants-2.24.x",
                ":pants-for-tests@parametrize=pants-2.23.x",
            ]
        }
    },
)

pex_binary(
    name="pants-for-tests",
    entry_point="pants",
    **parametrize(
        "pants-2.24.x",
        resolve="pants-2.24.x",
        dependencies=["3rdparty/python:pants-2.24.x#pantsbuild.pants"],
        output_path="pants-2.24.pex",
    ),
    **parametrize(
        "pants-2.23.x",
        resolve="pants-2.23.x",
        dependencies=["3rdparty/python:pants-2.23.x#pantsbuild.pants"],
        output_path="pants-2.23.pex",
    ),
)

python_distribution(
    name="wheel-2.24.x",
    provides=setup_py(
        name="shoalsoft-pants-telemetry-plugin-pants2.24.x",
        description="Pants Telemetry Plugin from Shoal Software LLC [Pants v2.24.x]",
        python_requires="==3.9.*",
        version="0.0.1",
    ),
    dependencies=["./register.py@resolve=pants-2.24.x"],
)

python_distribution(
    name="wheel-2.23.x",
    provides=setup_py(
        name="shoalsoft-pants-telemetry-plugin-pants2.23.x",
        description="Pants Telemetry Plugin from Shoal Software LLC [Pants v2.23.x]",
        python_requires="==3.9.*",
        version="0.0.1",
    ),
    dependencies=["./register.py@resolve=pants-2.23.x"],
)
