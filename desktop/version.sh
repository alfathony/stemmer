#!/bin/bash
# Prints the app version: the tag name without its "v" when building a tag
# like v0.2.0, otherwise the default below.
case "${GITHUB_REF:-}" in
  refs/tags/v*) echo "${GITHUB_REF#refs/tags/v}" ;;
  *) echo "0.1.0" ;;
esac
