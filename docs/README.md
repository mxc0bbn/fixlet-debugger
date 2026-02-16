# Fixlet Debugger for Linux

A PyQt5-based GUI wrapper for the BigFix `qna` command-line tool, providing similar functionality to the Windows Fixlet Debugger.

## Features

- **Syntax Highlighting**: Color-coded relevance language syntax matching Windows Fixlet Debugger colors
- **Smart Matching**: Parentheses, if-then-else, and "it" keyword matching with visual indicators
- **Multiple Query Evaluation**: Process multiple Q: lines at once
- **Zoom Support**: Ctrl+Mouse wheel or Ctrl++/-
- **Comments**: Single-line (//) and block (/* */) comments in green
- **Save/Load**: Save and load .qna files

## Prerequisites

- Ubuntu/Debian-based Linux (20.04+)
- BigFix Client installed (`/opt/BESClient/bin/qna`)

All other dependencies (Python 3, PyQt5, PolicyKit) are installed automatically by the package manager.

## Quick Install

```bash
# Install from .deb package (automatically installs all dependencies)
sudo apt install ./fixlet-debugger_1.2.1_all.deb

# Run
fixlet-debugger
```

## Manual Install

```bash
sudo ./install.sh
```

## Usage

```bash
sudo fixlet-debugger
# or
sudo python3 /opt/fixlet-debugger/fixlet_debugger.py
```

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| F5 / Ctrl+Enter | Evaluate queries |
| Ctrl+R | Remove results |
| Ctrl++/- | Zoom in/out |
| Ctrl+0 | Reset zoom |
| Ctrl+Mouse Wheel | Zoom |
| Ctrl+S | Save file |
| Ctrl+O | Open file |
| Ctrl+N | New file |
| Escape | Stop evaluation |

## Syntax Highlighting

- **Q:** queries in red
- **A:** answers in dark text
- **E:** errors with red background
- **Keywords** (if, then, else, of, whose, etc.) in blue
- **Strings** in teal
- **Numbers** in purple
- **Comments** (// and /* */) in green

## Smart Matching

- **Parentheses**: Matching brackets highlight in orange, unmatched persist in red
- **if-then-else**: All three keywords highlight when cursor is on any of them (parenthesis-aware)
- **"it" keyword**: Shows what "it" refers to with contextual highlighting

## Example

```
Q: name of operating system
Q: version of client
Q: number of processors
Q: (name of it, version of it) of operating system
Q: names of regapps whose (it contains "BES")
```

Press F5 to evaluate all queries.

## Building the .deb Package

```bash
./build.sh
```

## Acknowledgments

- HCL BigFix for the underlying qna binary
- Inspired by the Windows Fixlet Debugger included with BigFix
