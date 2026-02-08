// ==UserScript==
// @name         Monkeytype Custom Text Injector
// @namespace    http://tampermonkey.net/
// @version      0.1
// @description  Inject custom text into Monkeytype from localStorage
// @author       You
// @match        https://monkeytype.com/*
// @match        http://localhost:3000/*
// @grant        none
// @run-at       document-start
// ==/UserScript==

(function() {
    'use strict';

    // Check for injected text in a special localStorage key
    const injectedText = localStorage.getItem('rtc_injectedText');

    if (injectedText) {
        console.log('🐵 RealTypeCoach: Found injected text, applying...');

        try {
            const parsed = JSON.parse(injectedText);
            const words = parsed.text.split(/\s+/).filter(w => w.length > 0);

            const customTextSettings = {
                text: words,
                mode: parsed.mode || 'repeat',
                limit: {
                    value: words.length,
                    mode: "word"
                },
                pipeDelimiter: false
            };

            localStorage.setItem('customTextSettings', JSON.stringify(customTextSettings));

            // Clear the injection key so it doesn't persist
            localStorage.removeItem('rtc_injectedText');

            console.log('✅ RealTypeCoach: Text injected successfully! Reloading...');
        } catch (e) {
            console.error('❌ RealTypeCoach: Error injecting text:', e);
        }
    }
})();
