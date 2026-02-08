// Run this in the browser console on monkeytype.com
// Sets custom text and forces page reload

const text = "Das Nilpferd in der Achterbahn";
const words = text.split(/\s+/);

// Set custom text settings
const customTextSettings = {
    text: words,
    mode: "repeat",
    limit: {
        value: words.length,
        mode: "word"
    },
    pipeDelimiter: false
};

// Save to localStorage
localStorage.setItem('customTextSettings', JSON.stringify(customTextSettings));
localStorage.setItem('customTextName', 'rtc_' + Date.now());
localStorage.setItem('customTextLong', 'false');

// Set config to custom mode
const config = JSON.parse(localStorage.getItem('config') || '{}');
config.mode = 'custom';
localStorage.setItem('config', JSON.stringify(config));

console.log('Custom text set! Reloading...');

// Reload the page to apply changes
setTimeout(() => location.reload(), 500);
