# CPU Usage Investigation

**Date:** 2026-01-18
**Issue:** High CPU usage (~40-41%) observed during idle periods

> **UPDATE (2026-01-28):** A related device disconnection busy loop issue has been [fixed](./issues/device-disconnection-busy-loop-fix.md). This fix addresses high CPU usage when Bluetooth keyboards disconnect.

## Investigation Summary

Investigation conducted on a running RealTypeCoach instance (PID 2117937) that was consuming **41.3% CPU** continuously. The process was running for approximately 5 hours with abnormally high CPU usage despite minimal user activity.

### Key Findings

1. **Smoothing algorithm is NOT running on every burst** - The assumption that the centered moving average smoothing algorithm was causing the issue was **incorrect**.

2. **One thread consuming all CPU** - Thread 2118225 was using 41.4% CPU with **no wait channel** (WCHAN = "-"), indicating a tight loop doing active CPU work rather than waiting on I/O.

3. **Most likely cause: Qt method called from background thread** - The `EvdevHandler` calls `self.stats_panel.isVisible()` every second when the stats panel is visible, which is a Qt method being invoked from a non-GUI thread.

## Detailed Findings

### Smoothing Algorithm Usage

The `apply_moving_average()` function in `core/smoothing.py` is **only called** in these scenarios:

1. **On tab view** (`ui/stats_panel.py:867-878`): When the user switches to the "Trends" tab for the first time (lazy-loaded)
2. **On slider change** (`ui/wpm_graph.py:84-100`): When the user manually adjusts the "Aggregation" slider

Code flow:
```python
# ui/stats_panel.py:877-878
if index == 3 and not self._trend_data_loaded:
    self._trend_data_loaded = True
    if self._trend_data_callback is not None:
        self._trend_data_callback(self.wpm_graph.current_smoothness)
```

The `on_burst_complete` handler in `main.py:370-393` only updates basic statistics, recent bursts, and checks for high scores. It does **not** trigger trend graph updates.

### Suspected Cause: Thread-Safety Violation

**Location:** `core/evdev_handler.py:144-153`

```python
while not self._stop_event.is_set():
    # Use adaptive timeout: block indefinitely when stats panel hidden,
    # use 1s timeout when visible for responsive updates
    is_visible = (
        self.stats_panel_visible_getter()
        if self.stats_panel_visible_getter
        else self._stats_panel_visible
    )
    timeout = 1.0 if is_visible else None
    r, _, _ = select(devices, [], [], timeout)
```

**Problem:** The `stats_panel_visible_getter` is defined in `main.py:244` as:
```python
self.event_handler = EvdevHandler(
    event_queue=self.event_queue,
    layout_getter=self.get_current_layout,
    stats_panel_visible_getter=lambda: self.stats_panel.isVisible(),
)
```

**Issues:**
1. `isVisible()` is a Qt method that checks widget state
2. Calling Qt methods from a background (non-GUI) thread can cause:
   - Expensive thread-safety checks
   - Event processing overhead
   - Potential signal/slot invocations across threads
3. This happens **every second** when the stats panel is visible

### Other Potential Contributors

1. **Database encryption overhead** (`core/storage.py`):
   - SQLCipher with encrypted connections
   - Every query requires decryption
   - Connection pool with 10 max connections

2. **pyqtgraph rendering** (`ui/wpm_graph.py:45`):
   - `enableAutoRange()` called during init
   - Combined with explicit `setYRange()` calls
   - Potential rendering feedback loop

3. **ThreadPoolExecutor** (`main.py:97-99`):
   - Max 2 workers for background data fetching
   - Tasks submitted on slider changes
   - Could contribute if tasks are expensive

### Process State Analysis

**High-CPU thread (2118225):**
- WCHAN: "-" (no wait channel, actively running)
- CPU: 41.4% (consistent)
- Thread offset: +288 from main process

**Main thread (2117937):**
- WCHAN: "do_poll.constprop.0" (polling, normal)
- CPU: 0.1%

**All other threads:**
- WCHAN: "futex_wait_queue" (properly waiting)
- CPU: ~0%

## Algorithm Complexity Analysis

### Moving Average Smoothing (`core/smoothing.py`)

**Complexity:** O(n × window_size)

```python
for i in range(n):
    start = max(0, i - half_window)
    end = min(n, i + half_window + 1)
    window = wpm_values[start:end]
    result.append(sum(window) / len(window))
```

With:
- n = number of bursts (could be thousands)
- window_size = max(5, n × 0.20) = up to 20% of data

For 10,000 bursts with smoothness=100:
- window_size = 2,000
- Operations = 10,000 × 2,000 = 20,000,000 operations

**However, this only runs when the user changes the slider or opens the tab, not on every burst.**

### Database Query Complexity (`core/analyzer.py:557-565`)

```python
cursor.execute("SELECT avg_wpm FROM bursts ORDER BY start_time")
raw_wpm = [row[0] for row in cursor.fetchall() if row[0] is not None]
```

- Fetches ALL bursts from database
- With 1.9MB encrypted database, this could be thousands of records
- Each record requires decryption

**Again, this only runs on-demand, not continuously.**

## Recommendations

### High Priority

1. **Fix the `isVisible()` call from background thread:**
   - Cache visibility state and update via signal/slot from main thread
   - Or use a thread-safe flag that's updated when panel visibility changes

   ```python
   # In main.py
   self._stats_panel_visible = False  # Thread-safe flag

   def set_stats_panel_visibility(self, visible: bool):
       self._stats_panel_visible = visible

   # In evdev_handler
   stats_panel_visible_getter=lambda: self._stats_panel_visible
   ```

2. **Add instrumentation for better diagnosis:**
   - Thread CPU usage monitoring
   - Call count tracking for expensive operations
   - Log when smoothing calculations are performed

### Medium Priority

3. **Review auto-range configuration in graphs:**
   - Ensure `enableAutoRange()` is properly disabled when manually setting ranges
   - Check for rendering feedback loops

4. **Optimize smoothing algorithm:**
   - Use cumulative sum for O(n) complexity instead of O(n × window_size)
   - Cache smoothed results when smoothness=1 (raw data)

### Low Priority

5. **Database connection pooling:**
   - Review if 10 connections is necessary
   - Consider connection lifetime monitoring

## Testing Recommendations

1. **Reproduction test:**
   - Open stats panel with visible Trends tab
   - Monitor CPU usage over time
   - Check if CPU increases when Trends tab is visible

2. **Stress test:**
   - Large database (>10,000 bursts)
   - Rapid slider changes
   - Monitor thread CPU usage

3. **Profiling:**
   - Use `py-spy` or `pyinstrument` to get actual Python stack traces
   - Identify hot paths in production

## Resolution Status

**As of 2026-01-28:**
- **FIXED:** Device disconnection busy loop issue resolved
- See [Device Disconnection Busy Loop Fix](./issues/device-disconnection-busy-loop-fix.md) for details

**Previous status (2026-01-18):**
- Original high-CPU process (PID 2117937) has exited
- New process running at normal CPU usage (~1.8%)
- Root cause not definitively confirmed due to lack of debugging access
- Primary suspect remains `isVisible()` call from background thread

## Related Files

- `core/smoothing.py` - Moving average smoothing algorithm
- `core/evdev_handler.py` - Background keyboard event listener (suspected issue location)
- `core/analyzer.py:545-565` - `get_wpm_burst_sequence()` method
- `ui/wpm_graph.py` - WPM trend graph widget
- `ui/stats_panel.py:867-878` - Tab change handler with lazy loading
- `main.py:244` - EvdevHandler initialization with `isVisible()` lambda
- `main.py:370-393` - `on_burst_complete` handler
