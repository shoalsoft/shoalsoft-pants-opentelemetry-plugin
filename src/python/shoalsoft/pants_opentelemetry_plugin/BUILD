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

PLUGIN_VERSION = "0.1.1"

PANTS_MAJOR_MINOR_VERSIONS = ["2.26", "2.25", "2.21"]

python_sources(
    **parametrize(
        "pants-2.26",
        resolve="pants-2.26",
        interpreter_constraints=["==3.11.*"],
    ),
    **parametrize(
        "pants-2.25",
        resolve="pants-2.25",
        interpreter_constraints=["==3.11.*"],
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
        "pants-2.26",
        resolve="pants-2.26",
        interpreter_constraints=["==3.11.*"],
    ),
    **parametrize(
        "pants-2.25",
        resolve="pants-2.25",
        interpreter_constraints=["==3.11.*"],
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
        *(f":pex-{pants_version}" for pants_version in PANTS_MAJOR_MINOR_VERSIONS),
        *(
            f":pants-for-tests@parametrize=pants-{pants_version}"
            for pants_version in PANTS_MAJOR_MINOR_VERSIONS
        ),
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
        "pants-2.26",
        resolve="pants-2.26",
        interpreter_constraints=["==3.11.*"],
        dependencies=["3rdparty/python:pants-2.26#pantsbuild.pants"],
        output_path="pants-2.26.pex",
    ),
    **parametrize(
        "pants-2.25",
        resolve="pants-2.25",
        interpreter_constraints=["==3.11.*"],
        dependencies=["3rdparty/python:pants-2.25#pantsbuild.pants"],
        output_path="pants-2.25.pex",
    ),
    **parametrize(
        "pants-2.21",
        resolve="pants-2.21",
        interpreter_constraints=["==3.9.*"],
        dependencies=["3rdparty/python:pants-2.21#pantsbuild.pants"],
        output_path="pants-2.21.pex",
    ),
)


def declare_artifacts(pants_major_minor_version, python_version):
    pex_binary(
        name=f"pex-{pants_major_minor_version}",
        output_path=f"shoalsoft-pants-opentelemetry-plugin-pants{pants_major_minor_version}-v{PLUGIN_VERSION}.pex",
        interpreter_constraints=(f"=={python_version}.*",),
        dependencies=[
            f"./register.py@parametrize=pants-{pants_major_minor_version}",
            # Exclude Pants and its transitive dependencies since the Pants will supply those
            # dependencies itself from its own venv.
            f"!!3rdparty/python:pants-{pants_major_minor_version}#pantsbuild.pants",
        ],
        include_tools=True,
        resolve=f"pants-{pants_major_minor_version}",
    )
    python_distribution(
        name=f"wheel-{pants_major_minor_version}",
        interpreter_constraints=[f"=={python_version}.*"],
        provides=setup_py(
            name=f"shoalsoft-pants-opentelemetry-plugin-pants{pants_major_minor_version.replace('.', '')}",
            description=f"Pants OpenTelemetry Plugin from Shoal Software LLC [Pants v{pants_major_minor_version}.x]",
            python_requires=f"=={python_version}.*",
            version=PLUGIN_VERSION,
        ),
        dependencies=[
            f"./register.py@parametrize=pants-{pants_major_minor_version}",
            # Exclude Pants and its transitive dependencies since the Pants will supply those
            # dependencies itself from its own venv.
            f"!!3rdparty/python:pants-{pants_major_minor_version}#pantsbuild.pants",
        ],
    )


declare_artifacts("2.26", "3.11")
declare_artifacts("2.25", "3.11")
declare_artifacts("2.21", "3.9")
