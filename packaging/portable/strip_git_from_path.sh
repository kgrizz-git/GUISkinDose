#!/usr/bin/env bash
# Remove directories that contain a ``git`` executable from PATH; fail if git remains visible.
# Source this file, then call strip_git_from_path (used by CI and frozen png-check steps).

strip_git_from_path() {
    local entry new_path=""
    IFS=':' read -r -a parts <<<"$PATH"
    for entry in "${parts[@]}"; do
        [[ -n "$entry" ]] || continue
        if [[ -x "${entry%/}/git" ]]; then
            continue
        fi
        new_path="${new_path:+$new_path:}$entry"
    done
    export PATH="$new_path"
    command -v git >/dev/null && {
        echo "git on PATH" >&2
        return 1
    }
}
