# Pantsbuild OpenTelemetry Plugin

## Overview

This is a closed-source source-available plugin for the [Pantsbuild](https://pantsbuild.org/) build orchestration tool which emit tracing spans to OpenTelemetry-compatible systems.

Formating and type checks: `pants fmt lint check ::`

Tests: `pants test ::`

## Development Notes

### Manual Testing: OpenTelemetry

To manually test export of tracing spans using OTLP/HTTP:

1. Invoke Jarger's all-in-one image to provide a OpenTelemetry-compatible tracing span collector and UI. Run: `docker run --rm -e COLLECTOR_ZIPKIN_HOST_PORT=9411 -p 16686:16686 -p 4317:4317 -p 4318:4318 -p 9411:9411 jaegertracing/all-in-one:latest`

2. Modify a Pants project to set the `[GLOBAL].pythonpath` option to include the path `"/BASE_PATH_FOR_THIS_REPOSITORY/src/python"` and then set `[GLOBAL].backend_packages` to include `shoalsoft.pants_telemetry_plugin`.

3. Run Pants with `--shoalsoft-opentelemetry-enabled` and `--shoalsoft-opentelemetry-exporter=http`. The default endpoint configured in the OpenTelemetry library sends to http://localhost:4318 (on which the Docker image is listening).

4. View your traces in the Jaeger UI at http://localhost:16686.

### Workunits System

See [this documentation on the Pants streaming workunit handlers](docs/streaming-workunit-handlers.md) for information on how this plugin receives tracing data from the Pants core.

### Useful Links

- https://opentelemetry.io/docs/languages/python/
- https://opentelemetry-python.readthedocs.io/en/latest/
