#!/usr/bin/env python3
"""
Add a custom lesson to KTouch via SQLite database.
"""
import sqlite3
import uuid
import sys

DB_PATH = "~/.local/share/ktouch/profiles.db"

def add_custom_lesson(title: str, text: str, keyboard_layout: str = "us"):
    """Add a custom lesson to KTouch database."""
    lesson_id = str(uuid.uuid4())
    db_path = DB_PATH.replace("~", f"/home/{getpass.getuser()}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if we need a profile_id (for custom_lessons table)
    cursor.execute("SELECT id FROM profiles LIMIT 1")
    profile = cursor.fetchone()

    if not profile:
        print("No profile found in KTouch. Please run KTouch first to create a profile.")
        return False

    profile_id = profile[0]

    # Insert into custom_lessons table
    cursor.execute(
        "INSERT INTO custom_lessons (id, profile_id, title, text, keyboard_layout_name) VALUES (?, ?, ?, ?, ?)",
        (lesson_id, profile_id, title, text, keyboard_layout)
    )

    conn.commit()
    conn.close()

    print(f"Added custom lesson '{title}' to KTouch")
    print(f"Lesson ID: {lesson_id}")
    return True

if __name__ == "__main__":
    import getpass

    if len(sys.argv) < 3:
        print("Usage: ktouch_custom_lesson.py <title> <text>")
        print("Example: ktouch_custom_lesson.py 'Practice 1' 'The quick brown fox...'")
        sys.exit(1)

    title = sys.argv[1]
    text = " ".join(sys.argv[2:])
    add_custom_lesson(title, text)
