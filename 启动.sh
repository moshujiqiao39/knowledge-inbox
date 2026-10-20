#!/bin/sh
cd "$(dirname "$0")"
if command -v python3 >/dev/null 2>&1; then
  exec python3 start.py
fi
echo "Install Python 3.10 or newer."
exit 1
