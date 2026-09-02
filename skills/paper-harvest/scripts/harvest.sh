#!/usr/bin/env sh
if command -v paper-harvest >/dev/null 2>&1; then
  exec paper-harvest "$@"
fi
exec uvx paper-harvest "$@"
