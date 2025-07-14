# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

## [0.4.0] - 2025-07-14

- Removed gRPC support completely since there are fork safety issues with the gRPC C library used indirectly by the OpenTelemetry library. While there are mitigations, those mitigations only really work if the process stops forking at some point, and of course Pants is almost always forking to spawn build actions. Thus, the gRPC support has been removed for now so the plugin can focus on the working HTTP/Protobuf transport.
- Fixed a bug in how the plugin initialized its work unit handler.
- Async completion is disabled by default.

## [0.3.0] - 2025-07-11

- Try to properly support gRPC export by running gRPC span export in a subprocess so that the fork safety issues of the gRPC C library do not crash the Pants process.

## [0.2.2] - 2025-07-07

- Add `--shoalsoft-opentelemetry-async-completion` option to control the async completion feature of the work unit handler.
- Upgrade the Pants versions with which the plugin is tested to 2.27.0, 2.26.2, and 2.25.3.

## [0.2.1] - 2025-06-18

- Test plugin with Pants v2.27.0rc1.
- Upgrade OpenTelemetry dependencies to v1.34.1.

## [0.2.0] - 2025-06-11

This is the first non-dev release.

Changes since v0.2.0.dev3:

- Updated docs to show example Honeycomb configuration.
- Test the plugin with Pants v2.25.2 and v2.26.1.

[Unreleased]: https://github.com/shoalsoft/shoalsoft-pants-opentelemetry-plugin/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/shoalsoft/shoalsoft-pants-opentelemetry-plugin/releases/tag/v0.4.0
[0.3.0]: https://github.com/shoalsoft/shoalsoft-pants-opentelemetry-plugin/releases/tag/v0.3.0
[0.2.2]: https://github.com/shoalsoft/shoalsoft-pants-opentelemetry-plugin/releases/tag/v0.2.2
[0.2.1]: https://github.com/shoalsoft/shoalsoft-pants-opentelemetry-plugin/releases/tag/v0.2.1
[9.2.0]: https://github.com/shoalsoft/shoalsoft-pants-opentelemetry-plugin/releases/tag/v0.2.0
