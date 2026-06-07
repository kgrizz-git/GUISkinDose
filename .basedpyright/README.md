# Basedpyright baseline (optional)

This directory holds an **optional** type-check baseline when the project temporarily accepts known basedpyright errors during incremental typing.

**Current policy:** CI runs plain `basedpyright` with **no baseline** — any type error fails the build.

## Re-enable a baseline (temporary debt only)

1. Create or refresh the baseline file:

   ```bash
   ./scripts/type_baseline.sh write
   ```

2. Uncomment `baselineFile` in `pyproject.toml` if you want the IDE/CLI to pick it up without extra flags.

3. Commit `.basedpyright/baseline.json`.

4. CI: switch the `typecheck` job to `basedpyright --baselinefile .basedpyright/baseline.json` (lock mode in CI prevents silent baseline drift).

## After fixing baselined errors

Do **not** delete this file. Shrink it locally (auto-removes fixed diagnostics):

```bash
./scripts/type_baseline.sh shrink
git add .basedpyright/baseline.json
```

Use `write` only when **adding** new errors to the baseline. Use `shrink` (or a plain local `basedpyright --baselinefile …` run) when **removing** fixed errors.

## Remove baseline entirely

When error count reaches zero, delete `baseline.json`, comment out `baselineFile` in `pyproject.toml`, and restore plain `basedpyright` in CI.
