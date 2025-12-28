# RealTypeCoach

> **Improve your typing speed through data-driven insights**

RealTypeCoach is a **KDE Wayland typing analysis application** that tracks your typing patterns in real-time, helping you identify weaknesses and measure improvement.

![Typing Speed](https://img.shields.io/badge/Typing-40--120%20WPM-brightgreen)
![Python](https://img.shields.io/badge/Python-3.10+-blue)
![License](https://img.shields.io/badge/License-MIT-yellow)

## ✨ Features

### 🔍 Real-Time Statistics
- **Current WPM** - Track your typing speed live
- **Burst WPM** - See speed during active typing
- **Personal Best** - Daily high scores
- **Today's Stats** - Keystrokes, bursts, typing time

### 🐌 Identify Problem Keys
- **Slowest Keys** - Find which keys slow you down
- **Fastest Keys** - See your strongest keys
- **Per-Key Analysis** - Average press time for each key
- **Visual Feedback** - Easy-to-read rankings

### 🔒 Privacy First
- **Password Protection** - Automatic password field detection
- **No Cloud Sync** - All data stays local
- **No Telemetry** - We don't track your usage
- **Open Source** - Fully auditable code

### ⚡ Smart Analysis
- **Burst Detection** - Measures actual typing vs. pauses
- **High Score Tracking** - Celebrate your achievements
- **Daily Summaries** - Evening recap of your typing
- **Historical Data** - Track improvement over time

## 📸 Screenshots

### Statistics Panel
Shows your typing metrics including slowest and fastest keys.

### System Tray
Unobtrusive tray icon with context menu for quick access.

## 🚀 Quick Start

### Prerequisites

RealTypeCoach requires **KDE Plasma on Wayland** with these dependencies:

```bash
# Check if you have the required packages
dpkg -l | grep "python3-pyqt5"
python3 -c "import evdev; print('evdev OK')"
```

**Required packages:**
- `python3-pyqt5` - Qt5 GUI framework
- `evdev` - Python bindings for /dev/input/eventX

### Installation

#### 1. Install Dependencies

```bash
sudo apt update
sudo apt install python3-pyqt5
pip install evdev --user
```

#### 2. Add User to Input Group

```bash
sudo usermod -aG input $USER
# Log out and log back in for this to take effect
```

#### 3. Run RealTypeCoach

```bash
# Clone or download the repository
cd /path/to/realtypecoach

# Run the application
python3 main.py
```

**That's it!** The tray icon appears in your system tray.

### First Run

On first launch:
1. ✓ System tray icon appears (bottom-right)
2. ✓ Initial notification shown
3. ✓ Start typing normally
4. ✓ Click tray icon to view statistics

## 📖 How It Works

### Automatic Tracking

RealTypeCoach runs in the background:
- **Starts automatically** when you log in
- **Tracks every keystroke** (except passwords)
- **Updates statistics** in real-time
- **Works in any application** on your system

### View Statistics

**Click the tray icon** to see:
- Current typing speed (WPM)
- Top 10 slowest keys
- Top 10 fastest keys
- Today's total typing time
- Personal best WPM

### Daily Summary

At **18:00 (6 PM)** each day, you'll receive:
- Summary of your typing for the day
- Total keystrokes and typing time
- Your slowest key that day
- Personal best if achieved

**Configurable** in settings.

## 🎯 Using RealTypeCoach

### Step 1: Baseline (Week 1)

**Just type normally.**
- Don't try to change anything
- Let RealTypeCoach gather data
- Check your statistics daily
- Note your baseline WPM

### Step 2: Identify Weaknesses (Week 2)

**Review your slowest keys.**
- Which keys appear in your "Slowest Keys" list?
- Are there patterns? (pinky fingers, stretches, etc.)
- Focus on 1-2 keys at a time

### Step 3: Practice (Week 3-4)

**Targeted practice.**
- Practice your slowest keys deliberately
- Focus on accuracy first, then speed
- Use your normal applications (no games needed)
- Check statistics every few days

### Step 4: Measure Improvement (Ongoing)

**Track your progress.**
- Watch your WPM increase
- See slowest keys get faster
- Celebrate personal bests!
- Set new goals

## ⚙️ Configuration

### Settings Dialog

Right-click tray icon → **Settings**

**Available settings:**
- **Burst Timeout**: How long to wait before ending a burst (default: 3s)
- **High Score Duration**: Minimum burst for high score (default: 10s)
- **Keys to Show**: Number of slowest/fastest keys (default: 10)
- **Password Exclusion**: Ensure it's enabled (default: on)
- **Notification Time**: When to receive daily summary (default: 18:00)

### Data Management

**Export data:**
- Settings → Export to CSV
- Choose date range
- Save to file for analysis

**Clear data:**
- Settings → Clear Database
- Deletes all typing history
- Starts fresh

**Data retention:**
- Automatic deletion after 90 days
- Configurable via settings

## 📚 Learn More

### Concept Documentation

Detailed explanations of how RealTypeCoach works:

- **[Key Speed Metrics](concepts/key-speed-metrics.md)** - How key speed is calculated
- **[Burst Detection](concepts/burst-detection.md)** - How bursts are identified
- **[WPM Calculation](concepts/wpm-calculation.md)** - How WPM is computed
- **[Data Storage](concepts/data-storage.md)** - How data is stored and managed
- **[Privacy Protection](concepts/privacy-protection.md)** - How your privacy is protected

## 🔧 Troubleshooting

### "No keyboard events detected"

**Solution:** Check user is in input group
```bash
groups $USER | grep input
```

If not in input group:
```bash
sudo usermod -aG input $USER
# Log out and log back in
```

### "Icon not visible in system tray"

**Solution:** Check KDE system tray settings
- System Settings → Workspace Behavior → System Tray
- Ensure "Hidden Icons" can be shown

### "Application crashes on startup"

**Solution:** Check log file
```bash
cat /tmp/realtypecoach.log
```

### "Already running" error

**Solution:** Only one instance allowed
```bash
# Kill existing instance
just kill
# Or use kill.sh
./kill.sh
```

## 🛠️ Development

### Running Tests

```bash
# Run all tests
python3 -m pytest tests/ -v

# Run specific test
python3 -m pytest tests/test_analyzer.py -v
```

### Development Commands (using just)

```bash
just run       # Run the application
just kill      # Stop the application
just check     # Syntax check
```

## 📊 Typing Speed Benchmarks

| Level | WPM | Description |
|-------|-----|-------------|
| Beginner | 0-30 | Hunt and peck |
| Average | 40-50 | Typical office worker |
| Good | 50-70 | Touch typist |
| Fast | 70-90 | Experienced touch typist |
| Excellent | 90-120 | Professional typist |
| Exceptional | 120+ | Top 1% |

**Realistic improvement:** +10-30 WPM over 3 months with consistent practice.

## 🤝 Contributing

Contributions are welcome!

**Areas for contribution:**
- Bug fixes
- New features
- Documentation improvements
- Test coverage

**Development setup:**
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests
5. Submit a pull request

## 📄 License

MIT License - See LICENSE file for details

## 🙏 Acknowledgments

- **evdev** - Python bindings for reading /dev/input/eventX
- **PyQt5** - Python Qt bindings
- **SQLite** - Embedded database engine

## 📞 Support

- **Issues**: Report bugs via GitHub Issues
- **Questions**: Check documentation first
- **Feature Requests**: Welcome via GitHub Issues

---

**RealTypeCoach** - Type Faster, Work Smarter ⌨️
