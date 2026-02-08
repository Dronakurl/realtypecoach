# Monkeytype Integration Attempts

This document archives the various attempts to integrate RealTypeCoach with Monkeytype for practicing difficult words. These attempts were ultimately abandoned in favor of a simpler standalone typing practice page.

## Background

The goal was to allow users to practice their hardest words directly in Monkeytype, a popular typing test website. This would provide a familiar interface with advanced statistics and customization options.

## Attempts Overview

### 1. Firefox SQLite localStorage Injection
**Files:** `scripts/firefox_inject.py`, `scripts/firefox_inject_all.py`

**Approach:** Directly modify Firefox's SQLite database to inject custom text into Monkeytype's localStorage.

**Issues:**
- Complex database manipulation required
- Firefox would restore old values on close
- Database locking issues
- Private windows don't use persistent storage
- Different Firefox profiles have different storage paths

**Partial Success:** Could inject text and see it in database, but Firefox would overwrite values.

### 2. HTML-Based localStorage Injector
**Files:** `scripts/monkeytype_inject.html`, `scripts/monkeytype_inject_v2.html`

**Approach:** Create an HTML page that sets localStorage via JavaScript, then redirects to Monkeytype.

**Issues:**
- **Same-origin policy violation:** `file://` pages cannot access `https://monkeytype.com`'s localStorage
- Browsers isolate localStorage by domain for security
- The localStorage set on the HTML page was not accessible to Monkeytype

**Why It Failed:** Browser security prevents cross-domain localStorage access. This is a fundamental browser security feature.

### 3. Tampermonkey Userscript
**Files:** `scripts/monkeytype_autoinject.user.js`, `scripts/monkeytype_autoinject_v2.user.js`, `scripts/monkeytype_custom_text.user.js`, `scripts/monkeytype_injector.user.js`

**Approach:** Use Tampermonkey browser extension to inject JavaScript into Monkeytype page.

**Issues:**
- Requires users to install browser extension
- File:// URL access blocked by Chrome/Vivaldi
- GM_xmlhttpRequest couldn't read local files due to CORS
- Complex setup process for end users
- Cross-browser compatibility issues

**Partial Success:** The script worked when manually pasted in console, but automation was difficult.

### 4. HTTP Server Polling
**Files:** `scripts/monkeytype_server.py`, `scripts/open_monkeytype_with_text.py`

**Approach:** Run a local HTTP server that the userscript polls for injection data.

**Issues:**
- Requires running a background server
- Adds complexity to the application
- Still requires Tampermonkey extension
- More moving parts to maintain

**Status:** Not fully implemented.

### 5. Bookmarklet Approach
**Files:** `scripts/bookmarklet.html`

**Approach:** Create a bookmarklet that users click to inject text.

**Issues:**
- Still requires manual action (clicking bookmark)
- Not fully automated
- Poor user experience compared to one-click solution

## Why It Was Abandoned

### 1. Browser Security Fundamentals
The core issue is that browsers intentionally prevent cross-domain data access for security reasons. You cannot:
- Access localStorage from different domains
- Modify localStorage of external sites from your app
- Inject data into external websites without user action

### 2. User Experience Complexity
Even when technical workarounds existed, they required:
- Installing browser extensions
- Manually clicking bookmarks
- Pasting JavaScript code
- Running background servers

This violated the principle of providing a simple, one-click solution.

### 3. Browser Compatibility
Different browsers (Firefox, Chrome, Vivaldi) store data differently:
- Firefox: SQLite database with specific paths
- Chrome/Vivaldi: LevelDB format
- Private windows: No persistent storage

Supporting all browsers would require maintaining multiple code paths.

## The Solution: Standalone Typing Practice

Instead of fighting browser security, we created a standalone typing practice page that:

### Advantages
✅ **Simple:** One script, no extensions
✅ **Works everywhere:** Any browser, no setup
✅ **Reliable:** No cross-domain issues
✅ **Full control:** We own the entire experience
✅ **Same features:** WPM, accuracy, time tracking

### Features
- Custom text practice
- Real-time WPM calculation
- Accuracy tracking
- Timer display
- Tab to restart
- Responsive design
- Dark theme

## Lessons Learned

1. **Browser Security is Stringent:** Cross-domain data access is heavily restricted for good reasons
2. **User Experience Matters:** Complex technical solutions are not good if they confuse users
3. **Simplicity Wins:** Sometimes building your own solution is better than integrating with external services
4. **LocalStorage ≠ Shared Storage:** Each domain has its own isolated localStorage
5. **Private Windows are Different:** They don't use persistent storage, making testing difficult

## Files Preserved

The experimental scripts are preserved here for:
- Reference if integration becomes possible in the future
- Learning purposes
- Documentation of the development process
- Potential alternative approaches

## References

- [Monkeytype](https://monkeytype.com) - The typing practice website we tried to integrate with
- [Tampermonkey](https://www.tampermonkey.net/) - Browser extension used for userscript attempts
- [Same-origin policy](https://developer.mozilla.org/en-US/docs/Web/Security/Same-origin_policy) - The security policy that blocked our attempts

## Timeline

- **2026-02-08:** Initial attempts with Firefox SQLite injection
- **2026-02-08:** HTML-based injector attempts (failed due to same-origin policy)
- **2026-02-08:** Tampermonkey userscript development
- **2026-02-08:** HTTP server polling approach
- **2026-02-08:** Decision to use standalone typing practice page instead
- **2026-02-08:** Refactored application to use standalone practice page

---

**Conclusion:** While integration with Monkeytype seemed attractive, browser security and user experience considerations made it impractical. The standalone typing practice page provides a better solution for RealTypeCoach users.
