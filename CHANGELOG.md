# Changelog

All notable changes to this project will be documented in this file.

## [0.6.1] - 2026-06-28

> [!IMPORTANT]
> This release is likely the last version since this project is no longer actively maintained because Pants now has a built-in `pants.backend.observability.opentelemetry` backend (based on this plugin) in Pants v2.33 and later versions.

- Upgrade to Pants 2.32.1 and re-lock / upgrade dependencies.
- Update the README with non-maintained status.

## [0.6.0] - 2026-05-29

- This version of the plugin only supports Pants v2.32.x due to Pants switching from Python 3.11 to Python 3.14 for plugins. Use a prior version of the plugin for earlier Pants versions.
- This plugin will be available as the new `pants.backend.observability.opentelemetry` backend in Pants v2.33 and later. No more development will occur on this plugin.
- Add support for Pants v2.32 and drop support for prior Pants versions.
- Respect `OTEL_RESOURCE_ATTRIBUTES`.

## [0.5.0] - 2025-09-17

- Test the plugin with Pants v2.29.x.
- Discontinue testing the plugin with Pants v2.25.x.
- Use call-by-name syntax for rule invocations.

## [0.4.1] - 2025-07-24

- Support logging links to traces in a trace collection system via the new `[shoalsoft-opentelemetry].trace_link_template` option.
- Test the plugin with Pants v2.28.x.

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

[0.6.1]: https://github.com/shoalsoft/shoalsoft-pants-opentelemetry-plugin/releases/tag/v0.6.1
[0.6.0]: https://github.com/shoalsoft/shoalsoft-pants-opentelemetry-plugin/releases/tag/v0.6.0
[0.5.0]: https://github.com/shoalsoft/shoalsoft-pants-opentelemetry-plugin/releases/tag/v0.5.0
[0.4.1]: https://github.com/shoalsoft/shoalsoft-pants-opentelemetry-plugin/releases/tag/v0.4.1
[0.4.0]: https://github.com/shoalsoft/shoalsoft-pants-opentelemetry-plugin/releases/tag/v0.4.0
[0.3.0]: https://github.com/shoalsoft/shoalsoft-pants-opentelemetry-plugin/releases/tag/v0.3.0
[0.2.2]: https://github.com/shoalsoft/shoalsoft-pants-opentelemetry-plugin/releases/tag/v0.2.2
[0.2.1]: https://github.com/shoalsoft/shoalsoft-pants-opentelemetry-plugin/releases/tag/v0.2.1
[0.2.0]: https://github.com/shoalsoft/shoalsoft-pants-opentelemetry-plugin/releases/tag/v0.2.0
