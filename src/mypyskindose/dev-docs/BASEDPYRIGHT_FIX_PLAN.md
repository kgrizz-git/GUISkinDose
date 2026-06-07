# Basedpyright Type Error Fix Plan

## Overview
This plan outlines how to systematically resolve the 147 basedpyright type errors exposed after refreshing the baseline file. The goal is to fix actual bugs, improve type safety where practical, and baselining acceptable strictness warnings.

## Current Status
- **Total Errors**: 0 (resolved; CI uses strict `basedpyright` with no baseline)
- **Completed**: All categories from this plan — test file annotations, core type hints, optional guards, GUI/plotting fixes
- **Baseline policy**: removed committed baseline; use `./scripts/type_baseline.sh` only if reintroducing temporary debt (see `.basedpyright/README.md`)

## Error Categories & Fix Strategies

### Category 1: Test File Type Mismatches (High Priority)
**Files Affected**: `tests/unittests/test_geom_calc.py`
**Error Pattern**: 
```python
actual = [0] * len(expected)  # Creates list[int]
actual[6] = triangle.check_intersection(beam, cell)  # Assigns bool | list[bool]
```

**Fix Strategy**:
1. Add explicit type annotations to test variables
2. Use `list[bool | list[bool]]` for mixed-type lists
3. Consider using `typing.Any` for complex test assertions if needed

### Category 2: Dynamic Library Interactions (Medium Priority)
**Files Affected**: Multiple files in `src/mypyskindose/`
**Error Pattern**: 
- `reportAttributeAccessIssue`: Accessing attributes on dynamically typed objects
- `reportArgumentType`: Passing arguments to functions with strict type requirements

**Fix Strategy**:
1. Add explicit type annotations for function parameters and return values
2. Use `typing.cast()` when dealing with dynamic library returns
3. Add `# type: ignore[errorCode]` comments for known safe dynamic behavior

### Category 3: Missing Return Type Annotations (Medium Priority)
**Files Affected**: Core calculation files
**Error Pattern**: Functions returning complex types without explicit annotations

**Fix Strategy**:
1. Add return type hints to all public functions
2. Use `typing.Optional` for functions that may return None
3. Consider using `typing.Union` for multiple possible return types

### Category 4: Optional Member Access (Low Priority)
**Files Affected**: GUI and plotting files
**Error Pattern**: Accessing attributes on potentially None objects

**Fix Strategy**:
1. Add null checks before attribute access
2. Use `typing.Optional` annotations consistently
3. Consider using the `| None` syntax for Python 3.10+

## Implementation Steps

### Step 1: Fix Test File Errors (Immediate)
```bash
# Edit tests/unittests/test_geom_calc.py to fix type mismatches
# Change list initialization to use proper type annotations
```

### Step 2: Run Basedpyright & Categorize Remaining Errors
```bash
basedpyright --outputjson .basedpyright/errors.json
python scripts/categorize_errors.py .basedpyright/errors.json
```

### Step 3: Fix High-Priority Issues
- Focus on core calculation files first
- Add explicit type annotations where missing
- Fix actual bugs identified by the type checker

### Step 4: Address Medium-Priority Issues
- Handle dynamic library interactions
- Add return type annotations to public APIs
- Use baselining for acceptable strictness warnings

### Step 5: Resolve Low-Priority Issues
- Clean up optional member access warnings
- Improve GUI and plotting file types
- Final baseline refresh

## Tools & Scripts Needed

### Error Categorization Script
Create `scripts/categorize_errors.py` to group errors by type and file for efficient fixing.

### Baseline Management (optional — only if reintroducing known debt)

See `.basedpyright/README.md` and `scripts/type_baseline.sh`.

```bash
# After fixing baselined errors (auto-shrinks; commit the updated file):
./scripts/type_baseline.sh shrink

# Accept new known errors into baseline (rare):
./scripts/type_baseline.sh write
```

CI uses plain `basedpyright` while error count is zero. Do not delete the baseline file to shrink it — run `shrink` locally instead.