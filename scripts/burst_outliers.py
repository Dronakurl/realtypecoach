#!/usr/bin/env python3
"""Detect and display outliers in burst history.

Uses Isolation Forest algorithm to detect extreme outliers, with additional
filtering to ensure outliers are truly separated from the main distribution
(not just the tail).

Quartile statistics are shown for informational context.

Usage:
    python scripts/burst_outliers.py               # Show all outliers
    python scripts/burst_outliers.py --metric wpm  # Outliers by WPM
    python scripts/burst_outliers.py --top 20      # Show top N outliers
    python scripts/burst_outliers.py --gap-threshold 1.5  # Minimum gap as IQR multiple
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path
from statistics import median

import numpy as np
from sklearn.ensemble import IsolationForest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlcipher3 as sqlite3

from utils.crypto import CryptoManager

# Get database path
db_path = Path.home() / ".local" / "share" / "realtypecoach" / "typing_data.db"


def get_connection():
    """Get encrypted database connection."""
    if not db_path.exists():
        print(f"Error: Database not found at {db_path}")
        sys.exit(1)

    crypto = CryptoManager(db_path)
    key = crypto.get_key()

    if not key:
        print("Error: No encryption key found in keyring")
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    conn.execute(f"PRAGMA key = \"x'{key.hex()}'\"")
    return conn


def fetch_bursts(conn, metric: str):
    """Fetch bursts from database ordered by metric."""
    cursor = conn.cursor()

    # Map metric names to database columns
    metric_columns = {
        "wpm": "avg_wpm",
        "duration": "duration_ms",
        "key_count": "key_count",
        "net_keys": "net_key_count",
    }

    if metric not in metric_columns:
        print(f"Error: Unknown metric '{metric}'")
        print(f"Valid metrics: {', '.join(metric_columns.keys())}")
        sys.exit(1)

    column = metric_columns[metric]

    cursor.execute(
        f"""
        SELECT id, start_time, end_time, key_count, duration_ms, avg_wpm,
               backspace_count, net_key_count, qualifies_for_high_score
        FROM bursts
        WHERE {column} IS NOT NULL
        ORDER BY {column} DESC
        """
    )

    bursts = cursor.fetchall()
    return bursts, column


def calculate_quartiles(values):
    """Calculate quartile statistics.

    Returns:
        Tuple of (q1, q3, iqr)
    """
    sorted_values = sorted(values)
    n = len(sorted_values)

    def median_of_range(arr):
        if not arr:
            return 0
        return median(arr)

    mid = n // 2
    q1 = median_of_range(sorted_values[:mid])

    if n % 2 == 0:
        q3 = median_of_range(sorted_values[mid:])
    else:
        q3 = median_of_range(sorted_values[mid + 1 :])

    iqr = q3 - q1

    return q1, q3, iqr


def filter_by_gap(outlier_values, all_values, iqr, gap_threshold: float):
    """Filter outliers to only include those with a significant gap from non-outliers.

    This prevents treating the tail of a distribution as outliers.
    An outlier is kept only if there's a gap of at least (gap_threshold * IQR)
    between it and the nearest non-outlier value.

    Args:
        outlier_values: List of values flagged as outliers (sorted descending)
        all_values: All values in the dataset (sorted descending)
        iqr: Interquartile range of all values
        gap_threshold: Minimum gap as multiple of IQR

    Returns:
        List of outlier values that have sufficient gap
    """
    if not outlier_values:
        return []

    # Create set of outlier values for fast lookup
    outlier_set = set(outlier_values)

    # Find the maximum non-outlier value (the "boundary")
    max_non_outlier = None
    for v in all_values:
        if v not in outlier_set:
            max_non_outlier = v
            break

    if max_non_outlier is None:
        # All values are outliers, return them all
        return outlier_values

    min_gap_required = gap_threshold * iqr

    # Keep only outliers that are significantly above the max non-outlier
    filtered = []
    for v in outlier_values:
        gap = v - max_non_outlier
        if gap >= min_gap_required:
            filtered.append(v)

    return filtered


def detect_outliers(
    values,
    contamination: float = 0.01,
    gap_threshold: float = 1.0,
    random_state: int = 42,
):
    """Detect outliers using Isolation Forest with gap-based filtering.

    Args:
        values: List of numeric values
        contamination: Max expected proportion of outliers
        gap_threshold: Minimum gap from non-outliers as multiple of IQR
                      (higher = more selective, only extreme outliers)
        random_state: Random seed for reproducibility

    Returns:
        Tuple of (high_outlier_indices, low_outlier_indices, stats)
    """
    # Calculate quartiles for gap filtering
    q1, q3, iqr = calculate_quartiles(values)

    # Reshape for sklearn
    X = np.array(values).reshape(-1, 1)

    # Fit Isolation Forest
    clf = IsolationForest(
        contamination=contamination,
        random_state=random_state,
        n_estimators=100,
    )
    clf.fit(X)

    predictions = clf.predict(X)  # 1 = inlier, -1 = outlier
    scores = clf.score_samples(X)

    # Find outlier indices
    outlier_indices = [i for i, pred in enumerate(predictions) if pred == -1]

    # Separate into high and low outliers
    median_val = median(values)
    high_outlier_raw = [i for i in outlier_indices if values[i] > median_val]
    low_outlier_raw = [i for i in outlier_indices if values[i] < median_val]

    # Apply gap filtering to high outliers
    if high_outlier_raw:
        high_outlier_values = sorted([values[i] for i in high_outlier_raw], reverse=True)
        all_values_sorted = sorted(values, reverse=True)

        # For high outliers, find gap from highest non-outlier
        outlier_set = set(high_outlier_values)
        max_non_outlier = None
        for v in all_values_sorted:
            if v not in outlier_set:
                max_non_outlier = v
                break

        if max_non_outlier is not None:
            min_gap_required = gap_threshold * iqr
            high_outlier_indices = [
                i for i in high_outlier_raw if values[i] - max_non_outlier >= min_gap_required
            ]
        else:
            high_outlier_indices = high_outlier_raw
    else:
        high_outlier_indices = []

    # Apply gap filtering to low outliers
    if low_outlier_raw:
        low_outlier_values = sorted([values[i] for i in low_outlier_raw])
        all_values_sorted = sorted(values)

        # For low outliers, find gap from lowest non-outlier
        outlier_set = set(low_outlier_values)
        min_non_outlier = None
        for v in all_values_sorted:
            if v not in outlier_set:
                min_non_outlier = v
                break

        if min_non_outlier is not None:
            min_gap_required = gap_threshold * iqr
            low_outlier_indices = [
                i for i in low_outlier_raw if min_non_outlier - values[i] >= min_gap_required
            ]
        else:
            low_outlier_indices = low_outlier_raw
    else:
        low_outlier_indices = []

    stats = {
        "q1": q1,
        "q3": q3,
        "iqr": iqr,
        "median": median_val,
        "raw_outliers": len(outlier_indices),
        "high_raw": len(high_outlier_raw),
        "low_raw": len(low_outlier_raw),
    }

    return high_outlier_indices, low_outlier_indices, stats


def format_timestamp(ms: int) -> str:
    """Format millisecond timestamp to readable string."""
    return datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M:%S")


def format_duration(ms: int) -> str:
    """Format duration in milliseconds to readable string."""
    seconds = ms / 1000
    if seconds < 60:
        return f"{seconds:.1f}s"
    else:
        minutes = int(seconds // 60)
        secs = seconds % 60
        return f"{minutes}m {secs:.0f}s"


def print_outliers(
    bursts, metric_column: str, contamination: float, gap_threshold: float, top_n: int = None
):
    """Detect and print outliers."""
    if not bursts:
        print("No bursts found in database.")
        return

    col_to_idx = {
        "avg_wpm": 5,
        "duration_ms": 4,
        "key_count": 3,
        "net_key_count": 7,
    }
    metric_idx = col_to_idx[metric_column]

    values = [b[metric_idx] for b in bursts if b[metric_idx] is not None]

    if not values:
        print(f"No bursts with valid {metric_column} data.")
        return

    # Detect outliers
    high_outlier_indices, low_outlier_indices, stats = detect_outliers(
        values, contamination, gap_threshold
    )

    # Get bursts with scores for sorting
    high_outlier_bursts = [(bursts[i], values[i]) for i in high_outlier_indices]
    low_outlier_bursts = [(bursts[i], values[i]) for i in low_outlier_indices]

    # Sort by metric value (descending for high, ascending for low)
    high_outlier_bursts.sort(key=lambda x: x[1], reverse=True)
    low_outlier_bursts.sort(key=lambda x: x[1])

    high_outlier_bursts_only = [b for b, _ in high_outlier_bursts]
    low_outlier_bursts_only = [b for b, _ in low_outlier_bursts]

    print("=" * 80)
    print("BURST OUTLIERS ANALYSIS")
    print("=" * 80)
    print(f"\nTotal bursts: {len(bursts)}")
    print(f"Metric: {metric_column}")
    print("\nDistribution Statistics:")
    print(f"  Q1 (25th percentile): {stats['q1']:.2f}")
    print(f"  Median: {stats['median']:.2f}")
    print(f"  Q3 (75th percentile): {stats['q3']:.2f}")
    print(f"  IQR: {stats['iqr']:.2f}")

    print("\nDetection Method:")
    print(f"  Max contamination: {contamination:.1%}")
    print(f"  Gap threshold: {gap_threshold} × IQR = {gap_threshold * stats['iqr']:.2f}")
    print(f"  Raw outliers flagged: {stats['raw_outliers']}")
    print(f"  After gap filtering: {len(high_outlier_indices) + len(low_outlier_indices)}")
    print(f"    High outliers: {len(high_outlier_indices)}")
    print(f"    Low outliers: {len(low_outlier_indices)}")

    # Show high outliers
    if high_outlier_bursts_only:
        print(f"\n{'=' * 80}")
        print("HIGH OUTLIERS - Exceptional Performance")
    else:
        print("\nNo high outliers found (values are within normal distribution).")

    if high_outlier_bursts_only:
        print("=" * 80)

        display_outliers = high_outlier_bursts_only[:top_n] if top_n else high_outlier_bursts_only

        for i, b in enumerate(display_outliers, 1):
            (
                burst_id,
                start_time,
                end_time,
                key_count,
                duration_ms,
                avg_wpm,
                backspace_count,
                net_key_count,
                qualifies,
            ) = b
            metric_value = b[metric_idx]

            print(f"\n#{i}. Burst ID: {burst_id}")
            print(f"   Time: {format_timestamp(start_time)}")
            print(f"   {metric_column}: {metric_value:.2f}")

            if metric_column != "duration_ms":
                print(f"   Duration: {format_duration(duration_ms)}")
            if metric_column != "key_count":
                print(f"   Keys: {key_count} (net: {net_key_count})")
            if metric_column != "avg_wpm":
                print(f"   WPM: {avg_wpm:.1f}" if avg_wpm else "   WPM: N/A")

            if backspace_count:
                backspace_ratio = backspace_count / key_count if key_count else 0
                print(f"   Backspaces: {backspace_count} ({backspace_ratio:.1%})")

            if qualifies:
                print("   ★ Qualifies for high score")

    # Show low outliers
    if low_outlier_bursts_only:
        print(f"\n{'=' * 80}")
        print("LOW OUTLIERS - Below Expected Performance")
        print("=" * 80)

        display_outliers = low_outlier_bursts_only[:top_n] if top_n else low_outlier_bursts_only

        for i, b in enumerate(display_outliers, 1):
            (
                burst_id,
                start_time,
                end_time,
                key_count,
                duration_ms,
                avg_wpm,
                backspace_count,
                net_key_count,
                qualifies,
            ) = b
            metric_value = b[metric_idx]

            print(f"\n#{i}. Burst ID: {burst_id}")
            print(f"   Time: {format_timestamp(start_time)}")
            print(f"   {metric_column}: {metric_value:.2f}")

            if metric_column != "duration_ms":
                print(f"   Duration: {format_duration(duration_ms)}")
            if metric_column != "key_count":
                print(f"   Keys: {key_count} (net: {net_key_count})")
            if metric_column != "avg_wpm":
                print(f"   WPM: {avg_wpm:.1f}" if avg_wpm else "   WPM: N/A")


def main():
    parser = argparse.ArgumentParser(
        description="Detect statistical outliers in burst history using Isolation Forest with gap filtering",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                              # Show WPM outliers (default)
  %(prog)s --metric duration            # Show duration outliers
  %(prog)s --top 10                     # Show top 10 outliers only
  %(prog)s --gap-threshold 2.0          # Require 2×IQR gap (more selective)
  %(prog)s --contamination 0.05         # Allow up to 5%% to be considered

Metrics available:
  wpm       - Average words per minute
  duration  - Burst duration in milliseconds
  key_count - Total keystroke count
  net_keys  - Net keystrokes (excluding backspaces)

Detection Method:
  1. Isolation Forest identifies potential outliers (up to contamination rate)
  2. Gap filtering removes outliers that are too close to non-outliers
  3. Only values with a significant gap from the main distribution are shown

  This prevents treating the tail of a normal distribution as "outliers".
  Increase gap-threshold for more selective detection.
        """,
    )

    parser.add_argument(
        "--metric",
        "-m",
        choices=["wpm", "duration", "key_count", "net_keys"],
        default="wpm",
        help="Metric to analyze for outliers (default: wpm)",
    )
    parser.add_argument(
        "--top",
        "-n",
        type=int,
        help="Limit number of outliers displayed per category",
    )
    parser.add_argument(
        "--contamination",
        "-c",
        type=float,
        default=0.01,
        help="Max proportion of outliers to consider (default: 0.01 = 1%%)",
    )
    parser.add_argument(
        "--gap-threshold",
        "-g",
        type=float,
        default=1.0,
        help="Minimum gap from non-outliers as IQR multiple (default: 1.0×IQR)",
    )

    args = parser.parse_args()

    if not 0 < args.contamination < 0.5:
        print("Error: Contamination must be between 0 and 0.5")
        sys.exit(1)

    if args.gap_threshold < 0:
        print("Error: Gap threshold must be non-negative")
        sys.exit(1)

    conn = get_connection()

    try:
        bursts, metric_column = fetch_bursts(conn, args.metric)
        print_outliers(bursts, metric_column, args.contamination, args.gap_threshold, args.top)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
