// ==UserScript==
// @name         Monkeytype Custom Text
// @namespace    http://tampermonkey.net/
// @version      1.0
// @description  Inject custom text into Monkeytype
// @author       You
// @match        https://monkeytype.com/*
// @grant        none
// @run-at       document-start
// ==/UserScript==

(function() {
    'use strict';

    // Custom text to inject
    const CUSTOM_TEXT = "Das Nilpferd in der Achterbahn";

    // Override localStorage getItem/setItem to intercept config reads
    const originalGetItem = localStorage.getItem;
    const originalSetItem = localStorage.setItem;

    localStorage.getItem = function(key) {
        const result = originalGetItem.call(this, key);

        if (key === 'config') {
            console.log('[Monkeytype Injector] Intercepting config read');
            const config = JSON.parse(result || '{}');
            config.mode = 'custom';
            return JSON.stringify(config);
        }

        if (key === 'customTextSettings') {
            console.log('[Monkeytype Injector] Intercepting customTextSettings read');
            const words = CUSTOM_TEXT.split(/\s+/);
            return JSON.stringify({
                text: words,
                mode: 'repeat',
                limit: { value: words.length, mode: 'word' },
                pipeDelimiter: false
            });
        }

        return result;
    };

    // Also set the values directly
    const words = CUSTOM_TEXT.split(/\s+/);
    const textName = 'rtc_custom_' + Date.now();

    console.log('[Monkeytype Injector] Setting localStorage...');

    originalSetItem.call(localStorage, 'customTextSettings', JSON.stringify({
        text: words,
        mode: 'repeat',
        limit: { value: words.length, mode: 'word' },
        pipeDelimiter: false
    }));

    originalSetItem.call(localStorage, 'customTextName', textName);
    originalSetItem.call(localStorage, 'customTextLong', 'false');

    const customText = {};
    customText[textName] = CUSTOM_TEXT;
    originalSetItem.call(localStorage, 'customText', JSON.stringify(customText));

    const config = JSON.parse(originalGetItem.call(localStorage, 'config') || '{}');
    config.mode = 'custom';
    originalSetItem.call(localStorage, 'config', JSON.stringify(config));

    console.log('[Monkeytype Injector] Text injected:', CUSTOM_TEXT);
})();
