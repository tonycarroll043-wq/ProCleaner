# ProCleaner

**Free & open-source Windows system optimizer.**

![Windows](https://img.shields.io/badge/Windows-10%20%7C%2011-0078d4?logo=windows)
![License](https://img.shields.io/badge/license-MIT-green)
![Release](https://img.shields.io/github/v/release/tonycarroll043-wq/ProCleaner)
![Downloads](https://img.shields.io/github/downloads/tonycarroll043-wq/ProCleaner/total)

> One app to clean junk, fix the registry, manage startup, analyze disk space, and boost PC performance — no subscriptions, no ads, no tracking.

**[Download](https://github.com/tonycarroll043-wq/ProCleaner/releases/latest) · [Website](https://tonycarroll043-wq.github.io/ProCleaner/)**

---

## Features

| Tool | What it does |
|---|---|
| **PC Health Check** | Scores your system across 10 metrics (disk, RAM, CPU, junk, registry, updates…) |
| **Custom Cleaner** | Removes temp files, Windows cache, log files, installer leftovers |
| **Registry Cleaner** | Scans 8 categories — invalid paths, orphaned keys, broken COM refs — and fixes safely |
| **Browser Cleaner** | Clears Chrome/Edge cache, cookies, history |
| **Startup Manager** | View and disable programs that slow boot time |
| **Disk Analyzer** | Visual breakdown of what's eating storage |
| **Duplicate Finder** | Find and remove identical files |
| **Secure Wiper** | Multi-pass file erasure beyond recovery |
| **Uninstaller** | Remove software cleanly |
| **Software Updater** | Detect outdated software |
| **Performance Optimizer** | Tune Windows settings for speed |
| **Cookie Manager** | Granular browser cookie control |
| **Scheduler** | Automate cleaning on a schedule |

## Quick Start

1. Download [`ProCleaner-v1.0.0-Windows.zip`](https://github.com/tonycarroll043-wq/ProCleaner/releases/latest/download/ProCleaner-v1.0.0-Windows.zip)
2. Extract anywhere
3. Run `run.exe`

No Python required. No installation. Works on Windows 10 & 11.

## Run from Source

```bash
pip install -r requirements.txt
python main.py
```

## Build

```bash
pip install pyinstaller
pyinstaller ProCleaner.spec --clean --noconfirm
```

Output: `dist/ProCleaner/run.exe`

## License

MIT — free to use, modify, and distribute.
