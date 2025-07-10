# Copyright (C) 2025 Shoal Software LLC. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

PLUGIN_VERSION = "0.2.1"

PANTS_MAJOR_MINOR_VERSIONS = ["2.27", "2.26", "2.25"]

python_sources(
    sources=["*.py", "!*_test_server.py", "!*_test.py", "!*_integration_test.py"],
    overrides={
        "subprocess_processor.py": dict(
            dependencies=["./otlp_grpc_subprocess_processor_server.py"],
        )
    },
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
    overrides={
        "opentelemetry_integration_test.py": dict(
            dependencies=["./otlp_grpc_test_server.py:test_utils"],
        )
    },
    # Integration tests take forever given how they are run. :(
    timeout=600,
)

python_sources(
    name="test_utils",
    sources=["*_test_server.py"],
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

# This is a partial copy of the README.md geared more for the PyPI UX.
LONG_DESCRIPTION = """\
# Pantsbuild OpenTelemetry Plugin

## Overview

This is a plugin to the [Pantsbuild](https://pantsbuild.org/) build orchestration tool to emit tracing spans to OpenTelemetry-compatible systems for the build workflows orchestrated by Pants. The plugin is licensed under the [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0).

## Installation

From PyPI:

1. In the relevant Pants project, edit `pants.toml` to set the `[GLOBAL].plugins` option to include `shoalsoft-pants-opentelemetry-plugin` and the `[GLOBAL].backend_packages` option to include `shoalsoft.pants_opentelemetry_plugin`.

2. For basic export to a local OTLP/GRPC OpenTelemetry agent on its default port, configure the plugin as follows in `pants.toml`:

   ```toml
   [shoalsoft-opentelemetry]
   enabled = true
   exporter = "grpc"
   ```

3. The plugin exposes many other options (which correspond to `OTEL_` environment variables in other systems).  Run `pants help-advanced shoalsoft-opentelemetry` to see all of the plugin's available configuration options.

Note: The plugin respects any `TRACEPARENT` environment variable and will link generated traces to the parent trace and span referenced in the `TRACEPARENT`.

"""

# Add a single wheel which is not specific to any particular Pants version.
python_distribution(
    name=f"wheel",
    interpreter_constraints=[f"==3.11.*"],
    provides=setup_py(
        name="shoalsoft-pants-opentelemetry-plugin",
        description=f"Pantsbuild OpenTelemetry Plugin from Shoal Software LLC",
        long_description=LONG_DESCRIPTION,
        long_description_content_type="text/markdown",
        python_requires=f"==3.11.*",
        version=PLUGIN_VERSION,
        author="Tom Dyas",
        author_email="tom@shoalsoftware.com",
        url="https://github.com/shoalsoft/shoalsoft-pants-opentelemetry-plugin",
    ),
    dependencies=[
        f"./register.py@parametrize=pants-2.27",
        # Exclude Pants and its transitive dependencies since the Pants will supply those
        # dependencies itself from its own venv. This should also allow the plugin to be used
        # with any Pants version from Pants v2.25 and later.
        f"!!3rdparty/python:pants-2.27#pantsbuild.pants",
    ],
)
