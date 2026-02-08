# RealTypeCoach → Monkeytype Integration

Automatically open Monkeytype with custom text for practicing difficult words.

## One-Time Setup

### 1. Install Tampermonkey

Firefox extension: https://addons.mozilla.org/firefox/addon/tampermonkey/

### 2. Install the Userscript

1. Click the Tampermonkey icon in your browser
2. Select "Create a new script..."
3. Delete the default code
4. Copy the contents of `scripts/monkeytype_autoinject.user.js`
5. Paste it into the editor
6. Press `Ctrl+S` to save

Done! The userscript will now auto-inject text whenever you open Monkeytype.

## Usage

### From Command Line

```bash
python3 scripts/open_monkeytype_with_text.py "Das Nilpferd in der Achterbahn"
```

### From Python Application

```python
import subprocess

text = "Your difficult words here"
subprocess.run([
    "python3",
    "scripts/open_monkeytype_with_text.py",
    text
])
```

## How It Works

1. The Python script sets `rtc_inject_text` in Firefox's localStorage
2. Opens Monkeytype in Firefox
3. The Tampermonkey userscript detects the flag
4. Automatically injects the text and reloads the page
5. User can practice the custom text on Monkeytype!

## Advantages

- ✅ No manual console pasting
- ✅ Works with one button click from your app
- ✅ Clean user experience
- ✅ Uses full Monkeytype functionality
- ✅ Text automatically detected and injected

## Example Integration in RealTypeCoach

Add a button in your UI:

```python
def practice_difficult_words_clicked(self):
    # Get the difficult words from your analysis
    difficult_words = self.get_difficult_words()
    text = " ".join(difficult_words)

    # Open Monkeytype with the text
    subprocess.run([
        "python3",
        "scripts/open_monkeytype_with_text.py",
        text
    ])
```
