// ==UserScript==
// @name         RealTypeCoach - Monkeytype Integration
// @namespace    http://realtypecoach.local/
// @version      1.1
// @description  Auto-inject custom text from RealTypeCoach into Monkeytype
// @author       RealTypeCoach
// @match        https://monkeytype.com/*
// @grant        GM_xmlhttpRequest
// @connect      file://*
// @run-at       document-start
// ==/UserScript==

(function() {
    'use strict';

    const RTC_FILE = "file:///home/konrad/.rtc_monkeytype_text.txt";
    const MAX_AGE = 30000; // 30 seconds

    // Method 1: Check localStorage flag (for Firefox direct injection)
    const rtcText = localStorage.getItem('rtc_inject_text');
    const rtcTimestamp = localStorage.getItem('rtc_inject_timestamp');

    if (rtcText && rtcTimestamp) {
        const age = Date.now() - parseInt(rtcTimestamp);
        if (age < MAX_AGE) {
            injectText(rtcText);
            localStorage.removeItem('rtc_inject_text');
            localStorage.removeItem('rtc_inject_timestamp');
            return;
        }
    }

    // Method 2: Check file (works for all browsers with Tampermonkey)
    try {
        GM_xmlhttpRequest({
            method: "GET",
            url: RTC_FILE,
            onload: function(response) {
                try {
                    if (response.status === 200) {
                        const data = JSON.parse(response.responseText);
                        const age = Date.now() - data.timestamp;
                        if (age < MAX_AGE && data.text) {
                            console.log('[RTC] Reading text from file:', data.text.substring(0, 50));
                            injectText(data.text);
                        }
                    }
                } catch (e) {
                    console.log('[RTC] Could not read file:', e);
                }
            },
            onerror: function() {
                // File doesn't exist - normal, means no injection pending
                console.log('[RTC] No injection file found');
            }
        });
    } catch (e) {
        console.log('[RTC] GM_xmlhttpRequest not available');
    }

    function injectText(text) {
        console.log('[RTC] Injecting custom text:', text.substring(0, 60));

        const words = text.split(/\s+/);
        const textName = 'rtc_' + Date.now();

        // Clear any old values
        localStorage.removeItem('customTextSettings');
        localStorage.removeItem('customTextName');
        localStorage.removeItem('customTextLong');
        localStorage.removeItem('customText');

        // Set custom text settings
        const customTextSettings = {
            text: words,
            mode: 'repeat',
            limit: { value: words.length, mode: 'word' },
            pipeDelimiter: false
        };

        localStorage.setItem('customTextSettings', JSON.stringify(customTextSettings));
        localStorage.setItem('customTextName', textName);
        localStorage.setItem('customTextLong', 'false');

        // Save to customText collection
        const customText = {};
        customText[textName] = text;
        localStorage.setItem('customText', JSON.stringify(customText));

        // Update config to custom mode
        let config = {};
        try {
            config = JSON.parse(localStorage.getItem('config') || '{}');
        } catch(e) {}
        config.mode = 'custom';
        localStorage.setItem('config', JSON.stringify(config));

        console.log('[RTC] Text injected successfully! Page will reload to apply changes.');

        // Reload to apply changes
        setTimeout(() => {
            location.reload();
        }, 100);
    }
})();
