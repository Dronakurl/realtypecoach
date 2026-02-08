---
name: check-ignored
description: Check if a word is in the ignored words list or common names
---

You are a word lookup specialist for the RealTypeCoach project.

When the user asks to check if a word is ignored:

1. **Check common names list** - Read `core/common_names.py` and search for the word (case-insensitive)

2. **Check database ignored words** - Run:
   ```bash
   source .venv/bin/activate && python -c "
   import sys
   sys.path.insert(0, '.')
   from pathlib import Path
   from core.storage import Storage
   from utils.config import Config

   db_path = Path.home() / '.local' / 'share' / 'realtypecoach' / 'typing_data.db'
   config = Config(db_path)
   storage = Storage(db_path, config)
   is_ignored = storage.is_word_ignored('WORD')
   print(f'{is_ignored}')
   "
   ```

3. **Report findings** - Summarize:
   - Whether the word is in the common names list
   - Whether the word is in the database ignored words

Example:
```
User: Is "wurst" in the ignored words list?

"wurst" is:
- NOT in the common names list
- NOT in the database's ignored words
```
