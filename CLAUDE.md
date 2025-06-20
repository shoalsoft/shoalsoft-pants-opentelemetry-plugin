# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is a Pants plugin that enables OpenTelemetry tracing for Pantsbuild workflows. The plugin intercepts Pants workunits (internal tracing spans) and exports them to OpenTelemetry-compatible systems like Jaeger, Honeycomb, or local files.

## Development Commands

- **Format and lint**: `pants fmt lint check ::`
- **Run tests**: `pants test ::`  
- **Run integration tests**: `pants test src/python/shoalsoft/pants_opentelemetry_plugin:integration_tests`
- **Build wheel**: `pants package src/python/shoalsoft/pants_opentelemetry_plugin:wheel`
- **Build PEX artifacts**: `pants package src/python/shoalsoft/pants_opentelemetry_plugin:pex-2.27`

## Multi-Version Support

The plugin supports multiple Pants versions (2.25, 2.26, 2.27) using Pants' parametrize feature. Each version has its own lockfile in `3rdparty/python/pants-*.lock` and separate build targets. These lockfiles are mainly for integration testing. The distribution wheel is agnostic to Pants version.

## Architecture

### Core Components

- **register.py**: Main plugin registration with Pants engine using streaming workunit handlers
- **subsystem.py**: Configuration subsystem with all OpenTelemetry export options  
- **opentelemetry.py**: Core OpenTelemetry integration and span exporter implementations
- **processor.py**: Abstract processor interface for handling workunit lifecycle
- **workunit_handler.py**: Pants streaming workunit handler that receives workunit events
- **single_threaded_processor.py**: Thread-safe processor wrapper
- **exception_logging_processor.py**: Decorator processor for error handling

### Plugin Flow

1. Plugin registers with Pants via `WorkunitsCallbackFactoryRequest` union
2. Pants calls the factory to create `TelemetryWorkunitsCallback` instances  
3. Callback receives started/completed workunits from Pants engine
4. Workunits are converted to OpenTelemetry spans and exported

### Exporters

- **HTTP**: OTLP/HTTP exporter for OpenTelemetry collectors
- **GRPC**: OTLP/gRPC exporter for OpenTelemetry collectors  
- **JSON_FILE**: Debug exporter that writes spans to local JSON file

## Configuration

The plugin uses the `shoalsoft-opentelemetry` options scope. Key options:
- `enabled`: Enable/disable the plugin
- `exporter`: Choose HTTP/GRPC/JSON_FILE  
- `exporter_endpoint`: Target URL for HTTP/GRPC exporters
- `exporter_headers`: Headers for authentication (e.g., Honeycomb API keys)
- `parse_traceparent`: Enable TRACEPARENT environment variable parsing

## Testing

- Unit tests use pytest and test individual components
- Integration tests create temporary Pants projects and verify actual OTLP export
- Tests are parametrized across supported Pants versions
- Manual testing can use Jaeger all-in-one Docker image

## Code Style

- Python 3.11 interpreter constraints
- Black formatting (100 char line length)
- isort import sorting  
- flake8 linting with custom config in `build-support/flake8/.flake8`
- mypy type checking with strict settings