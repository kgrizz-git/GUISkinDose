#!/usr/bin/env bash
# Hide ``git`` from PATH; fail if git remains visible.
# Source this file, then call strip_git_from_path (used by CI and frozen png-check steps).
#
# On macOS and Linux git lives in /usr/bin beside cp, grep and the other tools a step
# needs, so dropping that directory breaks the step. Each directory that holds git is
# replaced by a shim directory of symlinks to everything in it except git.

strip_git_from_path() {
    local entry new_path="" shim tool name
    IFS=':' read -r -a parts <<<"$PATH"
    for entry in "${parts[@]}"; do
        [[ -n "$entry" ]] || continue
        # Every relative PATH entry is pinned to the current directory, so the
        # shim links still point at the right tools after a later cd.
        [[ "$entry" == /* ]] || entry="${PWD}/${entry}"
        if [[ -x "${entry%/}/git" ]]; then
            shim="$(mktemp -d)"
            for tool in "${entry%/}"/*; do
                name="${tool##*/}"
                [[ "$name" == git || "$name" == git-* ]] && continue
                ln -s "$tool" "${shim}/${name}"
            done
            entry="$shim"
        fi
        new_path="${new_path:+$new_path:}$entry"
    done
    export PATH="$new_path"
    hash -r
    command -v git >/dev/null && {
        echo "git on PATH" >&2
        return 1
    }
    return 0
}
