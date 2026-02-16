#!/bin/bash
#
# Fixlet Debugger for Linux - Manual Installation Script
# For Ubuntu/Zorin OS and other Debian-based distributions
# Use this as an alternative to the .deb package
#

set -e

INSTALL_DIR="/opt/fixlet-debugger"
DESKTOP_FILE="/usr/share/applications/fixlet-debugger.desktop"
POLKIT_DIR="/usr/share/polkit-1/actions"
POLKIT_FILE="${POLKIT_DIR}/com.bigfix.pkexec.fixlet-debugger.policy"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=================================="
echo "Fixlet Debugger for Linux Installer"
echo "=================================="
echo

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Please run this script with sudo:"
    echo "  sudo ./install.sh"
    exit 1
fi

# Check for Python 3
echo "[1/6] Checking for Python 3..."
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is not installed."
    echo "Install it with: sudo apt install python3"
    exit 1
fi
PYTHON_VERSION=$(python3 --version)
echo "  Found: $PYTHON_VERSION"

# Install PyQt5 if needed
echo
echo "[2/6] Checking for PyQt5..."
if ! python3 -c "import PyQt5" &> /dev/null; then
    echo "  PyQt5 not found. Installing..."
    apt update
    apt install -y python3-pyqt5
else
    echo "  PyQt5 is already installed."
fi

# Check for polkit
echo
echo "[3/6] Checking for PolicyKit..."
if ! command -v pkexec &> /dev/null; then
    echo "  PolicyKit not found. Installing..."
    apt update
    apt install -y policykit-1
else
    echo "  PolicyKit is already installed."
fi

# Create installation directory and install files
echo
echo "[4/6] Installing application..."
mkdir -p "$INSTALL_DIR"
cp "$SCRIPT_DIR/src/fixlet_debugger.py" "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR/fixlet_debugger.py"

# Create launcher script (invoked by pkexec as root)
cat > "$INSTALL_DIR/fixlet-debugger" << 'LAUNCHER'
#!/bin/bash
# Fixlet Debugger Launcher
# Invoked by pkexec — runs as root with DISPLAY/XAUTHORITY preserved

if [ -n "$PKEXEC_UID" ]; then
    export XDG_RUNTIME_DIR="/run/user/${PKEXEC_UID}"
    [ -z "$DISPLAY" ] && export DISPLAY=":0"
    if [ -z "$XAUTHORITY" ]; then
        USER_HOME=$(getent passwd "$PKEXEC_UID" | cut -d: -f6)
        [ -f "${USER_HOME}/.Xauthority" ] && export XAUTHORITY="${USER_HOME}/.Xauthority"
    fi
fi

exec /usr/bin/python3 /opt/fixlet-debugger/fixlet_debugger.py "$@"
LAUNCHER
chmod +x "$INSTALL_DIR/fixlet-debugger"

# Create pkexec wrapper for command-line access
cat > /usr/local/bin/fixlet-debugger << 'WRAPPER'
#!/bin/bash
# Fixlet Debugger — pkexec wrapper
# Provides graphical password prompt instead of requiring terminal sudo

if [ "$EUID" -eq 0 ]; then
    exec /opt/fixlet-debugger/fixlet-debugger "$@"
fi

exec pkexec /opt/fixlet-debugger/fixlet-debugger "$@"
WRAPPER
chmod +x /usr/local/bin/fixlet-debugger

# Install polkit policy
mkdir -p "$POLKIT_DIR"
cat > "$POLKIT_FILE" << 'POLICY'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE policyconfig PUBLIC "-//freedesktop//DTD PolicyKit Policy Configuration 1.0//EN"
 "http://www.freedesktop.org/standards/PolicyKit/1/policyconfig.dtd">
<policyconfig>
  <action id="com.bigfix.pkexec.fixlet-debugger">
    <description>Run Fixlet Debugger as root</description>
    <message>Authentication is required to run Fixlet Debugger</message>
    <icon_name>fixlet-debugger</icon_name>
    <defaults>
      <allow_any>auth_admin_keep</allow_any>
      <allow_inactive>auth_admin_keep</allow_inactive>
      <allow_active>auth_admin_keep</allow_active>
    </defaults>
    <annotate key="org.freedesktop.policykit.exec.path">/opt/fixlet-debugger/fixlet-debugger</annotate>
    <annotate key="org.freedesktop.policykit.exec.allow_gui">true</annotate>
  </action>
</policyconfig>
POLICY

echo "  Installed to: $INSTALL_DIR"

# Create desktop entry
echo
echo "[5/6] Creating desktop entry..."
cat > "$DESKTOP_FILE" << 'DESKTOP'
[Desktop Entry]
Version=1.1
Type=Application
Name=Fixlet Debugger
Comment=BigFix Relevance Expression Debugger
Exec=fixlet-debugger
Icon=fixlet-debugger
Terminal=false
Categories=Development;Utility;
Keywords=bigfix;relevance;debugger;qna;hcl;
StartupNotify=true
DESKTOP

if command -v update-desktop-database &> /dev/null; then
    update-desktop-database /usr/share/applications/ 2>/dev/null || true
fi

echo "  Desktop entry created."

# Check for qna binary
echo
echo "[6/6] Checking for BigFix qna binary..."
QNA_FOUND=false
for qna_path in "/opt/BESClient/bin/qna" "/opt/BESClient/qna"; do
    if [ -f "$qna_path" ]; then
        echo "  Found: $qna_path"
        QNA_FOUND=true
        if [ -x "$qna_path" ]; then
            echo "  Status: Executable"
        else
            echo "  WARNING: qna exists but is not executable"
            echo "  Run: sudo chmod +x $qna_path"
        fi
        break
    fi
done

if [ "$QNA_FOUND" = false ]; then
    echo "  WARNING: qna not found in standard locations"
    echo "  You can set the path in the application via Settings > Set QnA Path"
fi

echo
echo "=================================="
echo "Installation Complete!"
echo "=================================="
echo
echo "You can now launch Fixlet Debugger:"
echo
echo "  Option 1: From the application menu"
echo "            Search for 'Fixlet Debugger'"
echo
echo "  Option 2: From terminal"
echo "            fixlet-debugger"
echo
echo "A graphical password dialog will appear for authentication."
echo "No terminal window or sudo required!"
