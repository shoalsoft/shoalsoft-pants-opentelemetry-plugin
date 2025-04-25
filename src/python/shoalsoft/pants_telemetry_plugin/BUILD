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

PLUGIN_VERSION = "0.1.0"

python_sources(
    **parametrize(
        "pants-2.25",
        resolve="pants-2.25",
        interpreter_constraints=["==3.11.*"],
    ),
    **parametrize(
        "pants-2.24",
        resolve="pants-2.24",
        interpreter_constraints=["==3.9.*"],
    ),
    **parametrize(
        "pants-2.23",
        resolve="pants-2.23",
        interpreter_constraints=["==3.9.*"],
    ),
    **parametrize(
        "pants-2.21",
        resolve="pants-2.21",
        interpreter_constraints=["==3.9.*"],
    ),
)

python_tests(
    name="tests",
    sources=["*_test.py", "!*_integration_test.py"],
    **parametrize(
        "pants-2.25",
        resolve="pants-2.25",
        interpreter_constraints=["==3.11.*"],
    ),
    **parametrize(
        "pants-2.24",
        resolve="pants-2.24",
        interpreter_constraints=["==3.9.*"],
    ),
    **parametrize(
        "pants-2.23",
        resolve="pants-2.23",
        interpreter_constraints=["==3.9.*"],
    ),
    **parametrize(
        "pants-2.21",
        resolve="pants-2.21",
        interpreter_constraints=["==3.9.*"],
    ),
)

python_tests(
    name="integration_tests",
    sources=["*_integration_test.py"],
    interpreter_constraints=["==3.11.*"],
    runtime_package_dependencies=[
        ":wheel-2.25",
        ":wheel-2.24",
        ":wheel-2.23",
        ":wheel-2.21",
        ":pants-for-tests@parametrize=pants-2.25",
        ":pants-for-tests@parametrize=pants-2.24",
        ":pants-for-tests@parametrize=pants-2.23",
        ":pants-for-tests@parametrize=pants-2.21",
    ],
    # Integration tests take forever given how they are run. :(
    timeout=600,
)

pex_binary(
    name="pants-for-tests",
    entry_point="pants",
    execution_mode="venv",
    layout="zipapp",
    **parametrize(
        "pants-2.25",
        resolve="pants-2.25",
        interpreter_constraints=["==3.11.*"],
        dependencies=["3rdparty/python:pants-2.25#pantsbuild.pants"],
        output_path="pants-2.25.pex",
    ),
    **parametrize(
        "pants-2.24",
        resolve="pants-2.24",
        interpreter_constraints=["==3.9.*"],
        dependencies=["3rdparty/python:pants-2.24#pantsbuild.pants"],
        output_path="pants-2.24.pex",
    ),
    **parametrize(
        "pants-2.23",
        resolve="pants-2.23",
        interpreter_constraints=["==3.9.*"],
        dependencies=["3rdparty/python:pants-2.23#pantsbuild.pants"],
        output_path="pants-2.23.pex",
    ),
    **parametrize(
        "pants-2.21",
        resolve="pants-2.21",
        interpreter_constraints=["==3.9.*"],
        dependencies=["3rdparty/python:pants-2.21#pantsbuild.pants"],
        output_path="pants-2.21.pex",
    ),
)


def declare_pex_binary(version, python_version):
    pex_binary(
        name=f"pex-{version}",
        output_path=f"shoalsoft-pants-telemetry-plugin-pants{version}-v{PLUGIN_VERSION}.pex",
        interpreter_constraints=(f"=={python_version}.*",),
        dependencies=[
            f"./register.py@parametrize=pants-{version}",
            f"!!3rdparty/python:pants-{version}#pantsbuild.pants",
        ],
        include_tools=True,
    )


declare_pex_binary("2.25", "3.11")
declare_pex_binary("2.24", "3.9")
declare_pex_binary("2.23", "3.9")
declare_pex_binary("2.21", "3.9")
