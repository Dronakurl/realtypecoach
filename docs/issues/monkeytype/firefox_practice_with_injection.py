#!/usr/bin/env python3
"""
Launch Firefox with Monkeytype and inject custom text via JavaScript bookmarklet.

This opens Monkeytype and automatically injects custom text using a data URI that runs
JavaScript on the Monkeytype domain itself.
"""

import subprocess

# The custom text to inject
CUSTOM_TEXT = """javascript:(function(){
    const text = "Das Nilpferd in der Achterbahn";
    const words = text.split(/\\s+/);
    const textName = 'rtc_' + Date.now();

    localStorage.setItem('customTextSettings', JSON.stringify({
        text: words,
        mode: 'repeat',
        limit: { value: words.length, mode: 'word' },
        pipeDelimiter: false
    }));

    localStorage.setItem('customTextName', textName);
    localStorage.setItem('customTextLong', 'false');

    const customText = {};
    customText[textName] = text;
    localStorage.setItem('customText', JSON.stringify(customText));

    const config = JSON.parse(localStorage.getItem('config') || '{}');
    config.mode = 'custom';
    localStorage.setItem('config', JSON.stringify(config));

    alert('Text injected! Reloading...');
    location.reload();
})();"""


def launch():
    # Close Firefox first
    subprocess.run(["killall", "firefox"], stderr=subprocess.DEVNULL)
    subprocess.run(["sleep", "1"])

    # Open Monkeytype
    print("Opening Monkeytype...")
    print("IMPORTANT: After the page loads, PASTE this into the console (F12):")
    print("-" * 60)

    js_code = """const text = "Das Nilpferd in der Achterbahn";
const words = text.split(/\\s+/);
const textName = 'rtc_' + Date.now();

localStorage.setItem('customTextSettings', JSON.stringify({
    text: words,
    mode: 'repeat',
    limit: { value: words.length, mode: 'word' },
    pipeDelimiter: false
}));

localStorage.setItem('customTextName', textName);
localStorage.setItem('customTextLong', 'false');

const customText = {};
customText[textName] = text;
localStorage.setItem('customText', JSON.stringify(customText));

const config = JSON.parse(localStorage.getItem('config') || '{}');
config.mode = 'custom';
localStorage.setItem('config', JSON.stringify(config));

console.log('Text injected! Reloading...');
setTimeout(() => location.reload(), 500);"""

    print(js_code)
    print("-" * 60)

    subprocess.Popen(["firefox", "--new-window", "https://monkeytype.com"])


if __name__ == "__main__":
    launch()
