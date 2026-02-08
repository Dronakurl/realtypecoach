// ==UserScript==
// @name         RealTypeCoach - Monkeytype Integration
// @namespace    http://realtypecoach.local/
// @version      2.0
// @description  Auto-inject custom text from RealTypeCoach into Monkeytype
// @author       RealTypeCoach
// @match        https://monkeytype.com/*
// @grant        GM_getValue
# @grant        GM_setValue
# @run-at       document-start
// ==/UserScript==

(function() {
    'use strict';

    console.log('[RTC] Script loaded! Checking for injection...');

    const MAX_AGE = 30000; // 30 seconds

    // Get the injection data from Tampermonkey storage
    const injectedData = GM_getValue('rtc_inject_data', null);

    if (!injectedData) {
        console.log('[RTC] No injection data found');
        return;
    }

    const age = Date.now() - injectedData.timestamp;
    if (age > MAX_AGE) {
        console.log('[RTC] Injection data too old:', age, 'ms');
        GM_deleteValue('rtc_inject_data');
        return;
    }

    console.log('[RTC] Injecting text:', injectedData.text);
    injectText(injectedData.text);

    // Clear the data so we don't inject again
    GM_deleteValue('rtc_inject_data');

    function injectText(text) {
        console.log('[RTC] Starting injection...');

        const words = text.split(/\s+/);
        const textName = 'rtc_' + Date.now();

        localStorage.removeItem('customTextSettings');
        localStorage.removeItem('customTextName');
        localStorage.removeItem('customTextLong');
        localStorage.removeItem('customText');

        const customTextSettings = {
            text: words,
            mode: 'repeat',
            limit: { value: words.length, mode: 'word' },
            pipeDelimiter: false
        };

        localStorage.setItem('customTextSettings', JSON.stringify(customTextSettings));
        localStorage.setItem('customTextName', textName);
        localStorage.setItem('customTextLong', 'false');

        const customText = {};
        customText[textName] = text;
        localStorage.setItem('customText', JSON.stringify(customText));

        let config = {};
        try {
            config = JSON.parse(localStorage.getItem('config') || '{}');
        } catch(e) {}
        config.mode = 'custom';
        localStorage.setItem('config', JSON.stringify(config));

        console.log('[RTC] Injection complete! Reloading...');

        setTimeout(() => {
            location.reload();
        }, 100);
    }
})();
