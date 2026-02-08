# Monkeytype Custom Text Injector

## Method 1: Bookmarklet (Recommended)

1. **Create a bookmark** in Firefox:
   - Right-click bookmark bar → "New Bookmark"
   - Name: "Inject German Text"
   - Location (paste this code):

```javascript
javascript:(function(){const t="Das Nilpferd in der Achterbahn";const w=t.split(/\s+/);const n="rtc_"+Date.now();localStorage.setItem("customTextSettings",JSON.stringify({text:w,mode:"repeat",limit:{value:w.length,mode:"word"},pipeDelimiter:false}));localStorage.setItem("customTextName",n);localStorage.setItem("customTextLong","false");const c={};c[n]=t;localStorage.setItem("customText",JSON.stringify(c));const x=JSON.parse(localStorage.getItem("config")||"{}");x.mode="custom";localStorage.setItem("config",JSON.stringify(x));alert("Text injected!");location.reload()})()
```

2. **Use it:**
   - Go to https://monkeytype.com
   - Click the "Inject German Text" bookmark
   - Page will reload with your text!

## Method 2: Console Script

1. Go to https://monkeytype.com
2. Press F12 (Console)
3. Paste and run:

```javascript
const text = "Das Nilpferd in der Achterbahn";
const words = text.split(/\s+/);
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
setTimeout(() => location.reload(), 500);
```

## Why the SQLite injection didn't work:

The SQLite injection DOES work (we proved it with "The quick brown fox"), but there are two issues:

1. **Domain scoping**: HTML files on `file://` cannot access `https://monkeytype.com`'s localStorage
2. **Firefox persistence**: Firefox caches localStorage and may restore old values on close

The bookmarklet/console approach runs JavaScript ON the monkeytype.com domain itself, so it works reliably.
