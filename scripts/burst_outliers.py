#!/usr/bin/env python3
"""Detect and display outliers in burst history.

Uses Isolation Forest algorithm to detect extreme outliers.
This ML-based method is robust to various distributions and focuses on
anomalies rather than simple statistical deviations.

Quartile statistics are shown for informational context.

Usage:
    python scripts/burst_outliers.py               # Show all outliers
    python scripts/burst_outliers.py --metric wpm  # Outliers by WPM
    python scripts/burst_outliers.py --metric duration  # Outliers by duration
    python scripts/burst_outliers.py --top 20      # Show top N outliers
    python scripts/burst_outliers.py --contamination 0.02  # Set expected outlier ratio
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
    """Calculate quartile statistics for informational purposes.

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


def detect_outliers_isolation_forest(values, contamination: float = 0.05, random_state: int = 42):
    """Detect outliers using Isolation Forest algorithm.

    Isolation Forest is an unsupervised learning algorithm that identifies
    anomalies by isolating observations in a random forest. Anomalies are
    easier to isolate (require fewer splits), resulting in shorter path lengths.

    Args:
        values: List of numeric values
        contamination: Expected proportion of outliers in the dataset
                      (default: 0.05 = 5%, lower = more extreme outliers only)
        random_state: Random seed for reproducibility

    Returns:
        Tuple of (outlier_indices, outlier_scores)
        - outlier_indices: Indices of values that are outliers (-1 label)
        - outlier_scores: Anomaly scores (lower = more anomalous)
    """
    # Reshape for sklearn (needs 2D array)
    X = np.array(values).reshape(-1, 1)

    # Fit Isolation Forest
    clf = IsolationForest(
        contamination=contamination,
        random_state=random_state,
        n_estimators=100,
    )
    clf.fit(X)

    # Predict: 1 for inliers, -1 for outliers
    predictions = clf.predict(X)

    # Get anomaly scores (lower = more anomalous)
    scores = clf.score_samples(X)

    # Find outlier indices
    outlier_indices = [i for i, pred in enumerate(predictions) if pred == -1]

    return outlier_indices, scores


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


def print_outliers(bursts, metric_column: str, contamination: float, top_n: int = None):
    """Detect and print outliers using Isolation Forest."""
    if not bursts:
        print("No bursts found in database.")
        return

    # Extract metric values (index depends on column)
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

    # Calculate quartiles for informational context
    q1, q3, iqr = calculate_quartiles(values)

    # Detect outliers using Isolation Forest
    outlier_indices, scores = detect_outliers_isolation_forest(values, contamination)

    # Separate outliers into high and low based on metric value
    median_val = median(values)
    high_outliers = []
    low_outliers = []

    for idx in outlier_indices:
        burst = bursts[idx]
        score = scores[idx]
        if burst[metric_idx] > median_val:
            high_outliers.append((burst, score))
        else:
            low_outliers.append((burst, score))

    # Sort by anomaly score (most anomalous first for high, least anomalous first for low)
    # For high outliers, lower score = more anomalous, so we want to see those first
    high_outliers.sort(key=lambda x: x[1])  # ascending by score
    low_outliers.sort(key=lambda x: x[1])  # ascending by score

    # Convert back to just bursts with score tracking
    high_outlier_bursts = [b for b, _ in high_outliers]
    low_outlier_bursts = [b for b, _ in low_outliers]

    print("=" * 80)
    print("BURST OUTLIERS ANALYSIS")
    print("=" * 80)
    print(f"\nTotal bursts: {len(bursts)}")
    print(f"Metric: {metric_column}")
    print("\nQuartile Statistics (for context):")
    print(f"  Q1 (25th percentile): {q1:.2f}")
    print(f"  Q3 (75th percentile): {q3:.2f}")
    print(f"  IQR: {iqr:.2f}")
    print(f"  Median: {median_val:.2f}")
    print("\nIsolation Forest Detection:")
    print(f"  Contamination rate: {contamination:.1%}")
    print(
        f"  Outliers detected: {len(outlier_indices)} ({len(outlier_indices) / len(bursts) * 100:.1f}%)"
    )
    print(f"  High outliers: {len(high_outliers)}")
    print(f"  Low outliers: {len(low_outliers)}")

    # Show high outliers
    if high_outliers:
        print(f"\n{'=' * 80}")
        print("HIGH OUTLIERS - Exceptional Performance (sorted by anomaly)")
        print("=" * 80)

        # Limit to top_n if specified
        display_outliers = high_outlier_bursts[:top_n] if top_n else high_outlier_bursts

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

            # Additional context
            if metric_column != "duration_ms":
                print(f"   Duration: {format_duration(duration_ms)}")
            if metric_column != "key_count":
                print(f"   Keys: {key_count} (net: {net_key_count})")
            if metric_column != "avg_wpm":
                print(f"   WPM: {avg_wpm:.1f}" if avg_wpm else "   WPM: N/A")

            # Backspace info
            if backspace_count:
                backspace_ratio = backspace_count / key_count if key_count else 0
                print(f"   Backspaces: {backspace_count} ({backspace_ratio:.1%})")

            if qualifies:
                print("   ★ Qualifies for high score")

    # Show low outliers
    if low_outliers:
        print(f"\n{'=' * 80}")
        print("LOW OUTLIERS - Below Expected Performance (sorted by anomaly)")
        print("=" * 80)

        display_outliers = low_outlier_bursts[:top_n] if top_n else low_outlier_bursts

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
        description="Detect statistical outliers in burst history using Isolation Forest",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                              # Show WPM outliers (default)
  %(prog)s --metric wpm                 # Show WPM outliers
  %(prog)s --metric duration            # Show duration outliers
  %(prog)s --top 10                     # Show top 10 outliers only
  %(prog)s --contamination 0.02         # Only extreme 2%% outliers
  %(prog)s --contamination 0.10         # Show top 10%% as outliers

Metrics available:
  wpm       - Average words per minute
  duration  - Burst duration in milliseconds
  key_count - Total keystroke count
  net_keys  - Net keystrokes (excluding backspaces)

Isolation Forest Notes:
  Lower contamination = more extreme outliers only
  Default (0.05) = top/bottom 5%% most anomalous bursts
  The algorithm learns what "normal" looks like and flags bursts that
  deviate significantly from that pattern, regardless of distribution.
        """,
    )

    parser.add_argument(
        "--metric",
        choices=["wpm", "duration", "key_count", "net_keys"],
        default="wpm",
        help="Metric to analyze for outliers (default: wpm)",
    )
    parser.add_argument(
        "--top",
        type=int,
        help="Limit number of outliers displayed per category",
    )
    parser.add_argument(
        "--contamination",
        "-c",
        type=float,
        default=0.05,
        help="Expected proportion of outliers (default: 0.05 = 5%%, lower = more extreme only)",
    )

    args = parser.parse_args()

    if not 0 < args.contamination < 0.5:
        print("Error: Contamination must be between 0 and 0.5")
        sys.exit(1)

    conn = get_connection()

    try:
        bursts, metric_column = fetch_bursts(conn, args.metric)
        print_outliers(bursts, metric_column, args.contamination, args.top)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
