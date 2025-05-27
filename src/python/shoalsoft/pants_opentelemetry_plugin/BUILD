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

PLUGIN_VERSION = "0.2.0.dev0"

PANTS_MAJOR_MINOR_VERSIONS = ["2.27", "2.26", "2.25"]

python_sources(
    **parametrize(
        "pants-2.27",
        resolve="pants-2.27",
    ),
    **parametrize(
        "pants-2.26",
        resolve="pants-2.26",
    ),
    **parametrize(
        "pants-2.25",
        resolve="pants-2.25",
    ),
)

python_tests(
    name="tests",
    sources=["*_test.py", "!*_integration_test.py"],
    **parametrize(
        "pants-2.27",
        resolve="pants-2.27",
    ),
    **parametrize(
        "pants-2.26",
        resolve="pants-2.26",
    ),
    **parametrize(
        "pants-2.25",
        resolve="pants-2.25",
    ),
)

python_tests(
    name="integration_tests",
    sources=["*_integration_test.py"],
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
        "pants-2.27",
        resolve="pants-2.27",
        dependencies=["3rdparty/python:pants-2.27#pantsbuild.pants"],
        output_path="pants-2.27.pex",
    ),
    **parametrize(
        "pants-2.26",
        resolve="pants-2.26",
        dependencies=["3rdparty/python:pants-2.26#pantsbuild.pants"],
        output_path="pants-2.26.pex",
    ),
    **parametrize(
        "pants-2.25",
        resolve="pants-2.25",
        dependencies=["3rdparty/python:pants-2.25#pantsbuild.pants"],
        output_path="pants-2.25.pex",
    ),
)


def declare_pex_artifact(pants_major_minor_version):
    pex_binary(
        name=f"pex-{pants_major_minor_version}",
        output_path=f"shoalsoft-pants-opentelemetry-plugin-pants{pants_major_minor_version}-v{PLUGIN_VERSION}.pex",
        interpreter_constraints=(f"==3.11.*",),
        dependencies=[
            f"./register.py@parametrize=pants-{pants_major_minor_version}",
            # Exclude Pants and its transitive dependencies since the Pants will supply those
            # dependencies itself from its own venv.
            f"!!3rdparty/python:pants-{pants_major_minor_version}#pantsbuild.pants",
        ],
        include_tools=True,
        resolve=f"pants-{pants_major_minor_version}",
    )


for pants_version in PANTS_MAJOR_MINOR_VERSIONS:
    declare_pex_artifact(pants_version)


# Add a single wheel which is not specific to any particular Pants version.
python_distribution(
    name=f"wheel",
    interpreter_constraints=[f"==3.11.*"],
    provides=setup_py(
        name="shoalsoft-pants-opentelemetry-plugin",
        description=f"Pantsbuild OpenTelemetry Plugin from Shoal Software LLC",
        python_requires=f"==3.11.*",
        version=PLUGIN_VERSION,
    ),
    dependencies=[
        f"./register.py@parametrize=pants-2.27",
        # Exclude Pants and its transitive dependencies since the Pants will supply those
        # dependencies itself from its own venv. This should also allow the plugin to be used
        # with any Pants version from Pants v2.25 and later.
        f"!!3rdparty/python:pants-2.27#pantsbuild.pants",
    ],
)
