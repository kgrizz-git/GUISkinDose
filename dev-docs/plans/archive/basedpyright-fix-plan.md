# Basedpyright Type Error Fix Plan

> **Status: Completed (archived 2026-06-12).** All work shipped; CI runs strict `basedpyright` with no baseline. Policy: `.basedpyright/README.md`, `scripts/type_baseline.sh`.

## Overview

This plan outlined how to systematically resolve the 147 basedpyright type errors exposed after refreshing the baseline file. The goal was to fix actual bugs, improve type safety where practical, and baseline acceptable strictness warnings.

## Final status

- **Total errors**: 0
- **Completed**: test file annotations, core type hints, optional guards, GUI/plotting fixes
- **Baseline policy**: removed committed baseline; use `./scripts/type_baseline.sh` only if reintroducing temporary debt

## Error categories (historical)

### Category 1: Test file type mismatches

**Files affected**: `tests/unittests/test_geom_calc.py`

### Category 2: Dynamic library interactions

**Files affected**: multiple files in `src/mypyskindose/`

### Category 3: Missing return type annotations

**Files affected**: core calculation files

### Category 4: Optional member access

**Files affected**: GUI and plotting files

## Baseline management (optional — only if reintroducing known debt)

See `.basedpyright/README.md` and `scripts/type_baseline.sh`.

```bash
./scripts/type_baseline.sh shrink   # after fixing baselined errors
./scripts/type_baseline.sh write    # accept new known errors (rare)
```
