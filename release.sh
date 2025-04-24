#!/bin/sh

set -xeo pipefail

source ~/.keygen/secrets.sh

plugin_version="$1"
if [ -z "$plugin_version" ]; then
  echo "Usage: $0 <version>"
  exit 1
fi

for pants_version in 2.25 2.24 2.21 ; do
  pants_version_underscore="$(echo "$pants_version" | tr '.' '_')"
  pants_version_dash="$(echo "$pants_version" | tr '.' '-')"

  # Create a new version of this "package" in KeyGen.
  keygen new "--package=shoalsoft-pants-telemetry-plugin-pants${pants_version_dash}" --version="$plugin_version" || true

  # wheel
  keygen upload \
    "dist/shoalsoft_pants_telemetry_plugin_pants${pants_version}-${plugin_version}-py3-none-any.whl" \
    --package="shoalsoft-pants-telemetry-plugin-pants${pants_version_dash}" \
    --release="${plugin_version}" \
    --signing-key ~/.keygen/keygen.key

  # sdist
  keygen upload \
    "dist/shoalsoft_pants_telemetry_plugin_pants${pants_version_underscore}-${plugin_version}.tar.gz" \
    --package="shoalsoft-pants-telemetry-plugin-pants${pants_version_dash}" \
    --release="${plugin_version}" \
    --signing-key ~/.keygen/keygen.key

done


# Manually KeyGen.sh setup:
#
# 1. One-time: Created "package" for `shoalsoft-pants-telemetry-plugin-pants2-21` in Keygen UX.
#
# 2. Licenses
#
# Create User and/or Group instances.
#
# Create Policy with authentication strategy of LICENSE with relevant Product scope.
# Create License under that Policy for the relevant User or Group.
