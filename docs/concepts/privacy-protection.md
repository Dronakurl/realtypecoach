# Privacy Protection

## Overview

RealTypeCoach includes automatic **privacy protection** to ensure sensitive information (like passwords) is never recorded or analyzed.

## How Privacy Protection Works

### AT-SPI Password Field Detection

RealTypeCoach uses the **AT-SPI (Assistive Technology Service Provider Interface)** framework to detect when you're typing in a password field.

**How it works:**
1. AT-SPI provides accessibility information about UI elements
2. Password fields have a special "password text" flag
3. RealTypeCoach checks this flag for each key event
4. If in a password field → **Events are ignored**

### What Gets Blocked

When a password field is detected:
- ✓ **Keystrokes are NOT stored** in the database
- ✓ **Keystrokes are NOT analyzed** for statistics
- ✓ **Keystrokes are NOT counted** in WPM calculations
- ✓ **User is notified** via tray icon notification

### What Gets Logged

**Nothing is logged from password fields:**
- No keycodes
- No key names
- No timestamps
- No application names
- No typing patterns

**Completely ignored** - as if you never typed it.

## Password Field Detection

### Supported Applications

Any application using standard GTK/Qt widgets with proper AT-SPI accessibility:

**Works with:**
- ✓ Web browsers (Firefox, Chrome-based)
- ✓ GTK applications (GNOME apps)
- ✓ Qt applications (KDE apps)
- ✓ Electron apps (VS Code, Slack, etc.)
- ✓ Most native Linux applications

**May not work with:**
- ✗ Terminal-based applications (no AT-SPI)
- ✗ Some Wine/Windows apps
- ✗ Custom UI toolkits without accessibility
- ✗ Virtual machines / remote desktops

### Detection Signals

When password field detection triggers:

**Visual indicators:**
- Tray icon changes to paused state (yellow/orange)
- Tooltip shows "Monitoring Paused for Privacy"
- Notification appears: "Password Field Detected - Monitoring paused"

**When you leave the password field:**
- Notification: "Password Field Exited - Monitoring resumed"
- Tray icon returns to active state (blue)
- Normal monitoring resumes

### Automatic Resume

Monitoring **automatically resumes** when:
- You press Enter/Tab (common password confirmation)
- Click outside the password field
- Focus moves to another non-password element

**No manual intervention needed** - fully automatic.

## What Data IS Collected

For **non-password** typing, RealTypeCoach collects:

### Keystrokes
```
- Keycode (e.g., 30 = 'A' key)
- Key name (e.g., 'KEY_A')
- Timestamp (milliseconds since epoch)
- Application name (e.g., 'firefox', 'kate')
- Event type (press/release)
```

### What's NOT Collected
- **Actual text content** - We don't record what you type
- **Screen contents** - No screenshots or text capture
- **Clipboard** - Clipboard is never accessed
- **Audio/Video** - No media recording
- **Mouse** - Mouse movements/clicks not tracked
- **Internet** - No network communication

### What We CAN'T See
- Password content (even if we wanted to)
- Email bodies
- Chat messages (as text)
- Document content
- Code content

**Only**: Key press events (keycode, timestamp)

## Data Storage

### Local-Only Database

All data is stored in:
```
~/.local/share/realtypecoach/typing_data.db
```

- **SQLite database** on your local machine
- **No cloud storage** - never leaves your computer
- **No telemetry** - no data sent to developers
- **No analytics** - no tracking or usage statistics

### Database Schema

```sql
-- Key events (excluding password fields)
CREATE TABLE key_events (
    keycode INTEGER,          -- Physical key identifier
    key_name TEXT,            -- Human-readable name
    timestamp_ms INTEGER,     -- When pressed
    event_type TEXT,          -- 'press' or 'release'
    app_name TEXT,            -- Application (e.g., 'firefox')
    is_password_field INTEGER -- 1 if was password (0 = normal)
);

-- Note: is_password_field=1 events are never inserted
```

## Privacy Settings

### Current Implementation

Password field exclusion is:
- **Enabled by default**: Cannot be disabled
- **Always active**: No way to turn it off
- **Mandatory**: Part of the core privacy design

**Why no option to disable?**
- Security best practice
- Prevents accidental data collection
- Protects users from themselves
- Builds trust

### Future Enhancements (Planned)

Potential additional privacy features:
- Application blacklist (exclude certain apps)
- Time-based exclusion (work hours vs. personal)
- Manual pause/resume shortcut
- Incognito mode (temporary stop)

## Security Considerations

### Database Access

The database file permissions:
```
~/.local/share/realtypecoach/typing_data.db
- Owner: Your user
- Permissions: Read/write for owner only
- Group/Others: No access
```

**Protection:**
- Standard Linux file permissions
- Encrypted home directory support (if enabled)
- No sensitive data even if accessed (keycodes only)

### Data Export

When exporting data to CSV:
- Contains same data as database
- No additional privacy risks
- You control the export file
- Can delete after use

### Data Deletion

To delete all data:
```bash
rm ~/.local/share/realtypecoach/typing_data.db
```

Or use the application settings → "Clear Database"

## Privacy Guarantees

### What We Promise

1. **No password recording** - Ever, under any circumstances
2. **No cloud sync** - All data stays local
3. **No telemetry** - We don't track how you use the app
4. **No personal identification** - No names, emails, or IDs
5. **No text content** - Only keycodes and timestamps

### What We Recommend

1. **Review database** occasionally to verify
2. **Export/delete** data if concerned
3. **Use in work** - Safe for corporate environments
4. **Open source** - Code is auditable

### Transparency

- **Source code available**: Review it yourself
- **No hidden features**: What you see is what you get
- **No obfuscation**: Clear, readable code
- **No network code**: No network libraries used

## Limitations

### What We Can't Protect Against

1. **Physical access**: Someone with access to your computer
2. **System-level keyloggers**: Other malicious software
3. **Screen recording**: If someone records your screen
4. **Shoulder surfing**: Someone watching you type

### What We Don't Claim

- ❌ "Military-grade encryption" - It's a local SQLite DB
- ❌ "HIPAA compliant" - Not designed for medical data
- ❌ "Audit logging" - We don't log access attempts
- ❌ "Tamper-proof" - You can delete/edit the database

## Best Practices

### For Maximum Privacy

1. **Check notifications**: Ensure password detection is working
2. **Review database**: Query it occasionally
3. **Clear old data**: Don't keep data longer than needed
4. **Secure your account**: Use strong password, lock screen

### In Sensitive Environments

- **Corporate**: Check IT policy before installing
- **Shared computer**: Not recommended (other users could access DB)
- **High-security work**: Consult security team first

## Trust and Verification

### How to Verify

1. **Check the database**:
   ```bash
   sqlite3 ~/.local/share/realtypecoach/typing_data.db
   SELECT COUNT(*) FROM key_events WHERE is_password_field=1;
   # Should return: 0
   ```

2. **Monitor in real-time**:
   - Type in a password field
   - Check that keystroke counter doesn't increase
   - Verify notification appears

3. **Audit the code**:
   - Search for `is_password_field` in source
   - Verify events are filtered before storage
   - Check that no logging bypasses the filter

## Privacy Policy Summary

**We collect:**
- Keystroke timing data (keycode, timestamp)
- Application usage patterns (which app)
- Typing statistics (speed, bursts)

**We DON'T collect:**
- Passwords
- Text content
- Personal identification
- Sensitive information
- Network data

**Data storage:**
- Local only
- No cloud sync
- No sharing
- No selling

**Your rights:**
- Export your data
- Delete your data
- View the source code
- Audit the database
- Stop using at any time
