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

3. The plugin exposes many other options (which correspnd to `OTEL_` environment variables in other systems).  Run `pants help-advanced shoalsoft-opentelemetry` to see all of the plugin's available configuration options.

Note: The plugin respects any `TRACEPARENT` environment variable and will link generated traces to the parent trace and span referenced in the `TRACEPARENT`.

### Sample configuration: Honeycomb.io

To configure the plugin to send to [Honeycomb](https://www.honeycomb.io/), use the following configuration and replace `MY_HONEYCOMB_API_KEY` with your actual Honeycomb API key:

```toml
[shoalsoft-opentelemetry]
enabled = true
exporter = "grpc"
exporter_endpoint = "https://api.honeycomb.io"

[shoalsoft-opentelemetry.exporter_headers]
"x-honeycomb-team" = "MY_HONEYCOMB_API_KEY"
```

## Development

### Workflow

- Run formating and type checks (mypy): `pants fmt lint check ::`

- Run tests: `pants test ::`

- Build the wheel: `pants package src/python/shoalsoft/pants_opentelemetry_plugin:wheel`

### Manual Testing with Jaeger

To manually test export of tracing spans using OTLP/HTTP:

1. Invoke Jaeger's all-in-one image to provide a OpenTelemetry-compatible tracing span collector and UI. Run: `docker run --rm -e COLLECTOR_ZIPKIN_HOST_PORT=9411 -p 16686:16686 -p 4317:4317 -p 4318:4318 -p 9411:9411 jaegertracing/all-in-one:latest`

2. Modify a Pants project to set the `[GLOBAL].pythonpath` option to include the path `"/BASE_PATH_FOR_THIS_REPOSITORY/src/python"` and then set `[GLOBAL].backend_packages` to include `shoalsoft.pants_opentelemetry_plugin`.

3. Run Pants with `--shoalsoft-opentelemetry-enabled` and `--shoalsoft-opentelemetry-exporter=http`. The default endpoint configured in the OpenTelemetry library sends to http://localhost:4318 (on which the Docker image is listening).

4. View your traces in the Jaeger UI at http://localhost:16686.

Note: The integration tests do test that the plugin generates OTLP/HTTP and OTLP/GRPC to a local endpoint.

### Workunits System

See [this documentation on the Pants streaming workunit handlers](docs/streaming-workunit-handlers.md) for information on how this plugin receives tracing data from the Pants core.

### Useful Links

- https://opentelemetry.io/docs/languages/python/
- https://opentelemetry-python.readthedocs.io/en/latest/
