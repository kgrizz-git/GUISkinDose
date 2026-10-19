#!/bin/bash
# Double-click launcher for macOS: opens Terminal and runs run_gui.sh.
# run_gui.sh sets this file's Finder icon on its first run.
cd "$(dirname "$0")" || exit 1
./run_gui.sh "$@"
status=$?
if [ "$status" -ne 0 ]; then
    # Terminal may close the window on exit; keep the error readable.
    read -r -p "GUISkinDose exited with an error. Press Enter to close..." _
fi
exit "$status"
