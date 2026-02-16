# Fixlet Debugger for Linux — Installation Instructions

## System Requirements

- Ubuntu 20.04+ or other Debian-based Linux (tested on Zorin OS)
- HCL BigFix Client installed (with qna binary at `/opt/BESClient/bin/qna`)

All other dependencies (Python 3, PyQt5, PolicyKit) are installed automatically by the package manager.

## Installation

### Step 1: Install the Package

```bash
sudo apt install ./fixlet-debugger_1.2.1_all.deb
```

This will automatically install all required dependencies.

### Step 2: Run the Application

**From Applications Menu:**
- Find "Fixlet Debugger" in your applications menu
- A graphical password dialog will appear for authentication

**From Terminal:**
```bash
fixlet-debugger
```

## Quick Start Guide

1. **Launch the application** with sudo
2. **Type a relevance query** starting with `Q:`
   ```
   Q: name of operating system
   ```
3. **Press F5** or **Ctrl+Enter** to evaluate
4. **Results appear below** the query:
   ```
   Q: name of operating system
   A: Linux Ubuntu
   T: 0.070 ms
   ```

## Features

### Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| F5 | Evaluate all queries |
| Ctrl+Enter | Evaluate all queries |
| Ctrl+R | Remove all results (A:, T:, E: lines) |
| Ctrl++ | Zoom in |
| Ctrl+- | Zoom out |
| Ctrl+0 | Reset zoom |
| Ctrl+S | Save file |
| Ctrl+O | Open file |
| Ctrl+N | New file |

### Syntax Highlighting

- **Q:** queries in red
- **A:** answers in dark text
- **E:** errors with red background
- **Keywords** (if, then, else, of, whose, etc.) in blue
- **Strings** in teal
- **Numbers** in purple
- **Comments** (//) in green
- **Block comments** (/* */) in green

### Smart Matching

- **Parentheses**: Matching brackets highlight in orange, unmatched in red
- **if-then-else**: All three keywords highlight when cursor is on any of them
- **"it" keyword**: Shows what "it" refers to (contextual highlighting)

## Configuration

### Setting a Custom qna Path

If your BigFix client is installed in a non-standard location:

1. Go to **Settings → Set QnA Path**
2. Browse to your `qna` binary location
3. Common locations:
   - `/opt/BESClient/bin/qna` (default)
   - `/opt/BESClient/qna`

## Troubleshooting

### "Permission denied" error

```
Error: Permission denied accessing /var/opt/BESClient/...
```

**Solution**: Run with sudo:
```bash
sudo fixlet-debugger
```

### "qna binary not found"

**Solution**:
1. Verify BigFix client is installed: `ls /opt/BESClient/bin/qna`
2. Set custom path via Settings → Set QnA Path

### "The operator X is not defined"

This means the BigFix client doesn't have that inspector available. Some inspectors (like `debian packages`) may not be available in all client configurations. Try file-based alternatives.

### Application won't launch from desktop menu

If clicking the desktop icon doesn't work:
1. Open a terminal
2. Run: `sudo fixlet-debugger`

## Uninstalling

```bash
sudo dpkg -r fixlet-debugger
```
