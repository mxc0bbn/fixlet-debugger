#!/bin/bash
#
# Build script for Fixlet Debugger .deb package
#
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERSION="1.2.1"
PACKAGE_NAME="fixlet-debugger_${VERSION}_all"

echo "Building Fixlet Debugger .deb package v${VERSION}..."

# Copy the latest source into the debian package tree
cp "${SCRIPT_DIR}/src/fixlet_debugger.py" "${SCRIPT_DIR}/debian/opt/fixlet-debugger/fixlet_debugger.py"

# Remove any debug print statements from the packaged version
sed -i '/print(f"\[DEBUG\]/d' "${SCRIPT_DIR}/debian/opt/fixlet-debugger/fixlet_debugger.py"

# Clean up any __pycache__ directories from the package tree
rm -rf "${SCRIPT_DIR}/debian/opt/fixlet-debugger/__pycache__"

# Ensure polkit actions directory exists
mkdir -p "${SCRIPT_DIR}/debian/usr/share/polkit-1/actions"

# Ensure scripts are executable
chmod +x "${SCRIPT_DIR}/debian/DEBIAN/postinst"
chmod +x "${SCRIPT_DIR}/debian/DEBIAN/postrm"
chmod +x "${SCRIPT_DIR}/debian/opt/fixlet-debugger/fixlet-debugger"
chmod +x "${SCRIPT_DIR}/debian/opt/fixlet-debugger/fixlet_debugger.py"

# Verify Python syntax
echo "Checking Python syntax..."
python3 -m py_compile "${SCRIPT_DIR}/debian/opt/fixlet-debugger/fixlet_debugger.py" && echo "  Syntax OK"

# Build the .deb
dpkg-deb --build "${SCRIPT_DIR}/debian" "${SCRIPT_DIR}/${PACKAGE_NAME}.deb"

echo ""
echo "Package built: ${SCRIPT_DIR}/${PACKAGE_NAME}.deb"
echo ""
echo "To install (automatically resolves all dependencies):"
echo "  sudo apt install ./${PACKAGE_NAME}.deb"
