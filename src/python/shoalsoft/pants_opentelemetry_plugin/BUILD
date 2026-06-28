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

PLUGIN_VERSION = "0.6.1"

python_sources(
    sources=["*.py", "!*_test.py", "!*_integration_test.py"],
    resolve="pants-2.32",
    interpreter_constraints=["==3.14.*"],
)

python_tests(
    name="tests",
    sources=["*_test.py", "!*_integration_test.py"],
    resolve="pants-2.32",
    interpreter_constraints=["==3.14.*"],
)

python_tests(
    name="integration_tests",
    sources=["*_integration_test.py"],
    interpreter_constraints=["==3.14.*"],
    runtime_package_dependencies=[
        ":pants-for-tests",
        ":pex-2.32",
    ],
    # Integration tests take forever given how they are run. :(
    timeout=600,
)

pex_binary(
    name="pants-for-tests",
    entry_point="pants",
    execution_mode="venv",
    layout="zipapp",
    resolve="pants-2.32",
    dependencies=["3rdparty/python:pants-2.32#pantsbuild.pants"],
    output_path="pants-2.32.pex",
)

pex_binary(
    name=f"pex-2.32",
    output_path=f"shoalsoft-pants-opentelemetry-plugin-pants2.32-v{PLUGIN_VERSION}.pex",
    dependencies=[
        f"./register.py",
        # Exclude Pants and its transitive dependencies since the Pants will supply those
        # dependencies itself from its own venv.
        f"!!3rdparty/python:pants-2.32#pantsbuild.pants",
    ],
    include_tools=True,
    resolve=f"pants-2.32",
    interpreter_constraints=["==3.14.*"],
)

# This is a partial copy of the README.md geared more for the PyPI UX.
LONG_DESCRIPTION = """\
# Pantsbuild OpenTelemetry Plugin

## !!! NOT MAINTAINED !!!

- This project is no longer actively maintained because Pants now has a built-in `pants.backend.observability.opentelemetry` backend (based on this plugin) in Pants v2.33 and later versions.

- This version of the plugin only supports Pants v2.32 due to Pants switching to Python 3.14 for its internal Python version.

## Installation

From PyPI:

1. In the relevant Pants project, edit `pants.toml` to set the `[GLOBAL].plugins` option to include `shoalsoft-pants-opentelemetry-plugin` and the `[GLOBAL].backend_packages` option to include `shoalsoft.pants_opentelemetry_plugin`.

2. For basic export to a local OpenTelemetry collector agent on its default port, configure the plugin as follows in `pants.toml`:

   ```toml
   [shoalsoft-opentelemetry]
   enabled = true
   ```

3. The plugin exposes many other options (which correspond to `OTEL_` environment variables in other systems).  Run `pants help-advanced shoalsoft-opentelemetry` to see all of the plugin's available configuration options.

Note: The plugin respects any `TRACEPARENT` environment variable and will link generated traces to the parent trace and span referenced in the `TRACEPARENT`.
"""

# Add a single wheel which is not specific to any particular Pants version.
python_distribution(
    name=f"wheel",
    interpreter_constraints=[f"==3.14.*"],
    provides=setup_py(
        name="shoalsoft-pants-opentelemetry-plugin",
        description=f"Pantsbuild OpenTelemetry Plugin from Shoal Software LLC",
        long_description=LONG_DESCRIPTION,
        long_description_content_type="text/markdown",
        python_requires="==3.14.*",
        version=PLUGIN_VERSION,
        author="Tom Dyas",
        author_email="tom@shoalsoftware.com",
        url="https://github.com/shoalsoft/shoalsoft-pants-opentelemetry-plugin",
    ),
    dependencies=[
        f"./register.py",
        # Exclude Pants and its transitive dependencies since the Pants will supply those
        # dependencies itself from its own venv.
        f"!!3rdparty/python:pants-2.32#pantsbuild.pants",
    ],
)
