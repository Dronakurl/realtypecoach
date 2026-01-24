#!/usr/bin/env python3
"""Seed database with realistic typing data for testing and development."""

import argparse
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.storage import Storage
from utils.config import Config
from utils.crypto import CryptoManager
from utils.keyboard_detector import get_current_layout
from utils.keycodes import US_KEYCODE_TO_NAME

# Common English words for word statistics generation
COMMON_WORDS = [
    "the",
    "be",
    "to",
    "of",
    "and",
    "a",
    "in",
    "that",
    "have",
    "i",
    "it",
    "for",
    "not",
    "on",
    "with",
    "he",
    "as",
    "you",
    "do",
    "at",
    "this",
    "but",
    "his",
    "by",
    "from",
    "they",
    "we",
    "say",
    "her",
    "she",
    "or",
    "an",
    "will",
    "my",
    "one",
    "all",
    "would",
    "there",
    "their",
    "what",
    "so",
    "up",
    "out",
    "if",
    "about",
    "who",
    "get",
    "which",
    "go",
    "me",
    "when",
    "make",
    "can",
    "like",
    "time",
    "no",
    "just",
    "him",
    "know",
    "take",
    "people",
    "into",
    "year",
    "your",
    "good",
    "some",
    "could",
    "them",
    "see",
    "other",
    "than",
    "then",
    "now",
    "look",
    "only",
    "come",
    "its",
    "over",
    "think",
    "also",
    "back",
    "after",
    "use",
    "two",
    "how",
    "our",
    "work",
    "first",
    "well",
    "way",
    "even",
    "new",
    "want",
    "because",
    "any",
    "these",
    "give",
    "day",
    "most",
    "us",
]

# Longer words for variety
LONGER_WORDS = [
    "about",
    "above",
    "actor",
    "admit",
    "adult",
    "after",
    "again",
    "agent",
    "agree",
    "ahead",
    "alarm",
    "album",
    "alert",
    "alike",
    "alive",
    "allow",
    "alone",
    "along",
    "alter",
    "among",
    "anger",
    "angle",
    "angry",
    "apart",
    "apple",
    "apply",
    "arena",
    "argue",
    "arise",
    "array",
    "aside",
    "asset",
    "audio",
    "audit",
    "avoid",
    "award",
    "aware",
    "badly",
    "baker",
    "bases",
    "basic",
    "basis",
    "beach",
    "began",
    "begin",
    "begun",
    "being",
    "below",
    "bench",
    "billy",
    "birth",
    "black",
    "blame",
    "blind",
    "block",
    "blood",
    "board",
    "boost",
    "booth",
    "bound",
    "brain",
    "brand",
    "bread",
    "break",
    "breed",
    "brief",
    "bring",
    "broad",
    "broke",
    "brown",
    "build",
    "built",
    "buyer",
    "cable",
    "calm",
    "came",
    "canal",
    "candy",
    "carry",
    "catch",
    "cause",
    "chain",
    "chair",
    "chart",
    "chase",
    "cheap",
    "check",
    "chest",
    "chief",
    "child",
    "china",
    "chose",
    "civil",
    "claim",
    "class",
    "clean",
    "clear",
    "click",
    "clock",
    "close",
    "coach",
    "coast",
    "could",
    "count",
    "court",
    "cover",
    "craft",
    "crash",
    "cream",
    "crime",
    "cross",
    "crowd",
    "crown",
    "curve",
    "cycle",
    "daily",
    "dance",
    "dated",
    "dealt",
    "death",
    "debut",
    "delay",
    "depth",
    "doing",
    "doubt",
    "dozen",
    "draft",
    "drama",
    "drawn",
    "dream",
    "dress",
    "drill",
    "drink",
    "drive",
    "drove",
    "dying",
    "eager",
    "early",
    "earth",
    "eight",
    "elite",
    "empty",
    "enemy",
    "enjoy",
    "enter",
    "entry",
    "equal",
    "error",
    "event",
    "every",
    "exact",
    "exist",
    "extra",
    "faith",
    "false",
    "fault",
    "fiber",
    "field",
    "fifth",
    "fifty",
    "fight",
    "final",
    "first",
    "fixed",
    "flash",
    "fleet",
    "floor",
    "fluid",
    "focus",
    "force",
    "forth",
    "forty",
    "forum",
    "found",
    "frame",
    "frank",
    "fraud",
    "fresh",
    "front",
    "fruit",
    "fully",
    "funny",
    "giant",
    "given",
    "glass",
    "globe",
    "going",
    "grace",
    "grade",
    "grand",
    "grant",
    "grass",
    "great",
    "green",
    "gross",
    "group",
    "grown",
    "guard",
    "guess",
    "guest",
    "guide",
    "happy",
    "harry",
    "heart",
    "heavy",
    "hence",
    "hello",
    "horse",
    "hotel",
    "house",
    "human",
    "ideal",
    "image",
    "index",
    "inner",
    "input",
    "issue",
    "irony",
    "items",
    "japan",
    "jimmy",
    "joint",
    "jones",
    "judge",
    "known",
    "label",
    "large",
    "laser",
    "later",
    "laugh",
    "layer",
    "learn",
    "lease",
    "least",
    "leave",
    "legal",
    "level",
    "lewis",
    "light",
    "limit",
    "links",
    "lives",
    "local",
    "logic",
    "loose",
    "lower",
    "lucky",
    "lunch",
    "lying",
    "magic",
    "major",
    "maker",
    "march",
    "maria",
    "match",
    "maybe",
    "mayor",
    "meant",
    "media",
    "metal",
    "might",
    "minor",
    "minus",
    "mixed",
    "model",
    "money",
    "month",
    "moral",
    "motor",
    "mount",
    "mouse",
    "mouth",
    "movie",
    "music",
    "needs",
    "never",
    "newly",
    "night",
    "noise",
    "north",
    "noted",
    "novel",
    "nurse",
    "occur",
    "ocean",
    "offer",
    "often",
    "order",
    "other",
    "ought",
    "paint",
    "panel",
    "paper",
    "party",
    "peace",
    "phase",
    "phone",
    "photo",
    "piece",
    "pilot",
    "pitch",
    "place",
    "plain",
    "plane",
    "plant",
    "plate",
    "point",
    "pound",
    "power",
    "press",
    "price",
    "pride",
    "prime",
    "print",
    "prior",
    "prize",
    "proof",
    "proud",
    "prove",
    "queen",
    "quick",
    "quiet",
    "quite",
    "radio",
    "raise",
    "range",
    "rapid",
    "ratio",
    "reach",
    "ready",
    "refer",
    "right",
    "rival",
    "river",
    "robot",
    "roman",
    "rough",
    "round",
    "route",
    "royal",
    "rural",
    "scale",
    "scene",
    "scope",
    "score",
    "sense",
    "serve",
    "seven",
    "shall",
    "shape",
    "share",
    "sharp",
    "sheet",
    "shelf",
    "shell",
    "shift",
    "shirt",
    "shock",
    "shoot",
    "short",
    "shown",
    "sight",
    "since",
    "sixth",
    "sixty",
    "sized",
    "skill",
    "sleep",
    "slide",
    "small",
    "smart",
    "smile",
    "smith",
    "smoke",
    "solid",
    "solve",
    "sorry",
    "sound",
    "south",
    "space",
    "spare",
    "speak",
    "speed",
    "spend",
    "spent",
    "split",
    "spoke",
    "sport",
    "staff",
    "stage",
    "stake",
    "stand",
    "start",
    "state",
    "steam",
    "steel",
    "stick",
    "still",
    "stock",
    "stone",
    "stood",
    "store",
    "storm",
    "story",
    "strip",
    "stuck",
    "study",
    "stuff",
    "style",
    "sugar",
    "suite",
    "super",
    "sweet",
    "table",
    "taken",
    "taste",
    "taxes",
    "teach",
    "teeth",
    "terry",
    "texas",
    "thank",
    "theft",
    "their",
    "theme",
    "there",
    "these",
    "thick",
    "thing",
    "think",
    "third",
    "those",
    "three",
    "threw",
    "throw",
    "tight",
    "times",
    "tired",
    "title",
    "today",
    "topic",
    "total",
    "touch",
    "tough",
    "tower",
    "track",
    "trade",
    "train",
    "treat",
    "truck",
    "trust",
    "truth",
    "twice",
    "under",
    "undue",
    "union",
    "unity",
    "until",
    "upper",
    "upset",
    "urban",
    "usage",
    "usual",
    "valid",
    "value",
    "video",
    "virus",
    "visit",
    "vital",
    "voice",
    "waste",
    "watch",
    "water",
    "wheel",
    "where",
    "which",
    "while",
    "white",
    "whole",
    "whose",
    "woman",
    "women",
    "world",
    "worry",
    "worse",
    "worst",
    "worth",
    "would",
    "wound",
    "write",
    "wrong",
    "wrote",
    "yield",
    "young",
    "youth",
]


def get_letter_keys():
    """Get letter keycode mappings for the US layout."""
    letter_keys = []
    for keycode, key_name in US_KEYCODE_TO_NAME.items():
        if len(key_name) == 1 and key_name.isalpha():
            letter_keys.append((keycode, key_name))
    return letter_keys


def generate_bursts_for_day(day_start_ms: int, base_wpm: float, is_weekend: bool) -> list:
    """Generate burst data for a single day.

    Args:
        day_start_ms: Start of day in milliseconds since epoch
        base_wpm: Base WPM for this day (accounts for improvement over time)
        is_weekend: Whether this day is a weekend

    Returns:
        List of burst dictionaries
    """
    bursts = []

    # Fewer bursts on weekends
    if is_weekend:
        num_bursts = random.randint(5, 30)
    else:
        num_bursts = random.randint(10, 50)

    for _ in range(num_bursts):
        # Burst timing - spread throughout the day (9am-6pm typical work hours)
        hour = 9 + random.random() * 9  # 9-18
        start_offset = int(hour * 3600000)  # Convert to milliseconds
        start_time = day_start_ms + start_offset

        # Burst characteristics
        key_count = random.randint(20, 100)
        duration_ms = random.randint(2000, 10000)

        # WPM with variation around base
        wpm = base_wpm * random.uniform(0.7, 1.3)
        wpm = max(20, min(150, wpm))  # Clamp to realistic range

        end_time = start_time + duration_ms

        # Qualifies for high score? (min 10 seconds duration from config)
        qualifies = duration_ms >= 10000

        bursts.append(
            {
                "start_time": start_time,
                "end_time": end_time,
                "key_count": key_count,
                "duration_ms": duration_ms,
                "avg_wpm": wpm,
                "qualifies_for_high_score": qualifies,
            }
        )

    return bursts


def generate_slowest_key(layout: str, base_wpm: float) -> tuple[int, str]:
    """Generate a random slowest key for the day.

    Args:
        layout: Keyboard layout
        base_wpm: Base WPM (affects press times)

    Returns:
        Tuple of (keycode, key_name)
    """
    letter_keys = get_letter_keys()
    keycode, key_name = random.choice(letter_keys)

    # Typically slower keys
    if key_name in "qzxp":
        return (keycode, key_name)

    return (keycode, key_name)


def generate_key_statistics(storage: Storage, layout: str, base_wpm: float) -> None:
    """Generate key performance statistics.

    Args:
        storage: Storage instance
        layout: Keyboard layout
        base_wpm: Base WPM (affects press times)
    """
    letter_keys = get_letter_keys()

    # Base press time: 60 WPM = 5 chars/word = 12 chars/sec = ~83ms per key
    # Adjust based on WPM
    base_press_ms = 60000 / (base_wpm * 5)

    for keycode, key_name in letter_keys:
        # Add individual key variation
        key_factor = 1.0
        if key_name in "qzxp":  # Typically slower keys
            key_factor = 1.3
        elif key_name in "asdfghjkl":  # Home row - faster
            key_factor = 0.85

        press_time = base_press_ms * key_factor * random.uniform(0.8, 1.2)

        # Generate multiple updates to build realistic statistics
        total_presses = random.randint(50, 500)

        # Update statistics multiple times to build proper avg/slowest/fastest
        for _ in range(min(10, total_presses)):
            storage.update_key_statistics(
                keycode=keycode,
                key_name=key_name,
                layout=layout,
                press_time_ms=press_time * random.uniform(0.8, 1.2),
            )


def generate_word_statistics(storage: Storage, layout: str, base_wpm: float, num_days: int) -> None:
    """Generate word-level typing statistics.

    Args:
        storage: Storage instance
        layout: Keyboard layout
        base_wpm: Final base WPM (affects word speeds)
        num_days: Number of days to generate words for
    """
    # Combine common and longer words
    all_words = COMMON_WORDS + LONGER_WORDS

    # Base press time per letter
    base_ms_per_letter = 60000 / (base_wpm * 5)

    # Generate statistics for random subset of words
    num_words_to_gen = min(len(all_words), 100 + num_days // 2)
    selected_words = random.sample(all_words, num_words_to_gen)

    for word in selected_words:
        num_letters = len(word)
        if num_letters < 3:
            continue

        # Speed varies with word length and complexity
        complexity_factor = 1.0 + (num_letters * 0.02)
        avg_speed_ms = base_ms_per_letter * complexity_factor * random.uniform(0.8, 1.2)

        # Generate multiple observations
        observation_count = random.randint(2, 20)
        total_duration_ms = int(avg_speed_ms * num_letters * observation_count)

        # Some editing time
        backspace_count = random.randint(0, 5) if random.random() < 0.3 else 0
        editing_time_ms = backspace_count * random.randint(100, 500)

        # Use the internal connection method to update word statistics
        # We need to bypass the normal word detection flow
        now_ms = int(datetime.now().timestamp() * 1000)

        with storage._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO word_statistics
                (word, layout, avg_speed_ms_per_letter, total_letters,
                 total_duration_ms, observation_count, last_seen,
                 backspace_count, editing_time_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    word,
                    layout,
                    avg_speed_ms,
                    num_letters,
                    total_duration_ms,
                    observation_count,
                    now_ms,
                    backspace_count,
                    editing_time_ms,
                ),
            )
            conn.commit()


def seed_database(days: int, layout: str, db_path: Path) -> None:
    """Main seeding function.

    Args:
        days: Number of days to generate data for
        layout: Keyboard layout identifier
        db_path: Path to database
    """
    print(f"Seeding database for {days} days...")
    print(f"Database: {db_path}")
    print(f"Layout: {layout}")
    print()

    # Calculate end date (today) and start date
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    # Base WPM (will improve over time)
    base_wpm = 40.0
    wpm_improvement = 30.0 / days  # 30 WPM improvement over the period

    days_with_data = 0
    total_bursts = 0
    total_keystrokes = 0

    # Initialize storage
    crypto = CryptoManager(db_path)
    if not crypto.key_exists():
        print("No encryption key found. Initializing new key...")
        crypto.initialize_database_key()

    config = Config(db_path)
    storage = Storage(db_path, config=config)

    # Clear existing data (user preference: always clear)
    print("Clearing existing data...")
    storage.clear_database()
    print("Database cleared.")
    print()

    # Generate data for each day
    for day_offset in range(days):
        current_date = start_date + timedelta(days=day_offset)
        date_str = current_date.strftime("%Y-%m-%d")
        day_start_ms = int(current_date.timestamp() * 1000)

        # Skip some days (simulate gaps)
        if random.random() < 0.15:  # 15% chance of no data
            continue

        # Reduce weekend activity
        is_weekend = current_date.weekday() >= 5
        if is_weekend and random.random() < 0.3:  # 30% chance on weekends
            continue

        # Calculate current WPM (with improvement)
        current_wpm = base_wpm + (day_offset * wpm_improvement)

        # Generate bursts
        bursts = generate_bursts_for_day(day_start_ms, current_wpm, is_weekend)

        if not bursts:
            continue

        # Store bursts
        for burst in bursts:
            storage.store_burst(
                start_time=burst["start_time"],
                end_time=burst["end_time"],
                key_count=burst["key_count"],
                duration_ms=burst["duration_ms"],
                avg_wpm=burst["avg_wpm"],
                qualifies_for_high_score=burst["qualifies_for_high_score"],
            )

        total_bursts += len(bursts)

        # Calculate daily summary
        daily_keystrokes = sum(b["key_count"] for b in bursts)
        daily_bursts = len(bursts)
        daily_avg_wpm = sum(b["avg_wpm"] for b in bursts) / daily_bursts
        daily_typing_sec = sum(b["duration_ms"] for b in bursts) // 1000

        # Generate slowest key
        keycode, key_name = generate_slowest_key(layout, current_wpm)

        # Update daily summary
        storage.update_daily_summary(
            date=date_str,
            total_keystrokes=daily_keystrokes,
            total_bursts=daily_bursts,
            avg_wpm=daily_avg_wpm,
            slowest_keycode=keycode,
            slowest_key_name=key_name,
            total_typing_sec=daily_typing_sec,
        )

        total_keystrokes += daily_keystrokes

        # Generate high scores for exceptional bursts
        qualifying = [b for b in bursts if b["qualifies_for_high_score"]]
        if qualifying:
            best = max(qualifying, key=lambda b: b["avg_wpm"])
            storage.store_high_score(
                date=date_str,
                wpm=best["avg_wpm"],
                duration_ms=best["duration_ms"],
                key_count=best["key_count"],
            )

        days_with_data += 1

        # Progress every 10 days
        if (day_offset + 1) % 10 == 0:
            print(f"  Generated {day_offset + 1}/{days} days...")

    # Generate key statistics
    print("Generating key statistics...")
    final_wpm = base_wpm + (days * wpm_improvement)
    generate_key_statistics(storage, layout, final_wpm)

    # Generate word statistics
    print("Generating word statistics...")
    generate_word_statistics(storage, layout, final_wpm, days)

    print()
    print(f"Done! Generated data for {days_with_data} days")
    print(f"Total bursts: {total_bursts}")
    print(f"Total keystrokes: {total_keystrokes}")
    print(f"Average WPM progression: {base_wpm:.1f} -> {final_wpm:.1f}")


def main():
    """Main entry point for database seeding."""
    parser = argparse.ArgumentParser(description="Seed database with realistic typing data")
    parser.add_argument(
        "--days",
        type=int,
        default=365,
        help="Number of days to generate data for (default: 365)",
    )
    parser.add_argument(
        "--layout",
        type=str,
        default=None,
        help="Keyboard layout (default: auto-detect)",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=None,
        help="Custom database path (default: ~/.local/share/realtypecoach/typing_data.db)",
    )
    args = parser.parse_args()

    # Auto-detect layout if not specified
    layout = args.layout
    if layout is None:
        try:
            layout = get_current_layout()
            print(f"Auto-detected keyboard layout: {layout}")
        except Exception as e:
            print(f"Could not auto-detect layout: {e}")
            print("Using default layout: us")
            layout = "us"

    # Determine database path
    if args.db_path:
        db_path = args.db_path
    else:
        db_path = Path.home() / ".local" / "share" / "realtypecoach" / "typing_data.db"

    # Create parent directory if needed
    db_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        seed_database(args.days, layout, db_path)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
