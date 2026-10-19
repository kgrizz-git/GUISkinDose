#!/bin/bash
# Double-click launcher for macOS: opens Terminal and runs run_gui.sh.
# run_gui.sh sets this file's Finder icon on its first run.
cd "$(dirname "$0")" || exit 1
exec ./run_gui.sh "$@"
