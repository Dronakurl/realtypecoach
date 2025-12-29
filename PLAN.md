# Plan: Threading Safety and Code Quality Improvements

## Summary

Fix thread safety issues in `keyboard_detector.py` and similar issues in `core/analyzer.py` and `core/evdev_handler.py`, while standardizing threading patterns across the codebase. Keep the code simple and avoid over-engineering.

## Issues Found

### 1. keyboard_detector.py (Critical)
- **Thread safety**: `self.running` checked/modified without locks
- **stop() doesn't stop**: `join(timeout=1)` won't interrupt `sleep()`
- **Code duplication**: `get_current_layout()` and `get_available_layouts()` repeat same logic
- **Magic numbers**: `timeout=5` repeated 4 times
- **Inconsistent parsing**: Line 94 has redundant check

### 2. core/analyzer.py (Same threading issues)
- Lines 52-53, 59-63: Same `self.running` pattern without locks
- Same `stop()` issue with `join(timeout=1)`

### 3. core/evdev_handler.py (Less critical but inconsistent)
- Uses `self.running` flag with `select(timeout=0.1)` (better but not ideal)
- Inconsistent with notification_handler.py which uses `threading.Event()` correctly

### 4. core/dictionary.py
- Line 127: Uses `os.path.exists()` instead of `Path.exists()`

### 5. Good Pattern (notification_handler.py)
- **Correctly uses `threading.Event()`** for stopping (lines 46, 151-152, 158)
- This is the pattern we should standardize on

## Implementation Plan

### Phase 1: Fix keyboard_detector.py

1. **Extract helper function** to eliminate duplication:
   ```python
   def _query_layout_source(source) -> Optional[list[str]]:
       """Returns list of layouts from a source, or None if unavailable."""
   ```
   - Consolidate the 4 detection methods (XKB, localectl, /etc/default/keyboard, setxkbmap)
   - Single helper used by both `get_current_layout()` and `get_available_layouts()`

2. **Fix threading using `threading.Event()`**:
   - Replace `self.running` + `self._lock` with `threading.Event()`
   - Use `event.wait(interval)` instead of `time.sleep(interval)`
   - Follow the pattern from `notification_handler.py`

3. **Add constants** for magic values:
   ```python
   SUBPROCESS_TIMEOUT = 5  # seconds
   DEFAULT_LAYOUT = 'us'
   ```

4. **Clean up redundant parsing** (line 94)

### Phase 2: Apply fixes to analyzer.py

1. Use `threading.Event()` for background loop
2. Keep lock only for data access, not for lifecycle control
3. Remove redundant `if self.running` checks

### Phase 3: Apply fixes to evdev_handler.py

1. Use `threading.Event()` for cleaner shutdown
2. Remove `self.running` flag

### Phase 4: Fix dictionary.py

1. Replace `os.path.exists(path)` with `Path(path).exists()`
2. Already imports `Path` from pathlib (line 3)

## What We're NOT Doing (to keep it simple)

- **No base class for thread management**: Would be over-engineering for just 3 classes
- **No pydantic for keyboard detection**: Layout detection is simple string operations, not worth the overhead
- **No config class for magic numbers**: Module-level constants are sufficient
- **No major refactoring**: Just fixing the specific issues identified

## Files to Modify

1. `utils/keyboard_detector.py` - Main fixes
2. `core/analyzer.py` - Threading fixes only
3. `core/evdev_handler.py` - Threading fixes only
4. `core/dictionary.py` - pathlib fix only

## Testing Strategy

- Run `just test-all` after each phase
- Verify thread lifecycle:
  - start() called twice → no duplicate threads
  - stop() completes quickly → doesn't wait for full sleep interval
  - start() → stop() → start() → works correctly
