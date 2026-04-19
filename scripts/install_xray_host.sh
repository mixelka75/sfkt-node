#!/bin/bash
set -e

echo "=========================================="
echo "SFKT Node - Xray Host Installation"
echo "=========================================="

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "ERROR: Please run as root"
    exit 1
fi

# Pin a known-good Xray release. XHTTP still evolves on main, so pinning avoids
# breaking changes between deploys. Override with XRAY_VERSION=vX.Y.Z.
# Known good for stream-one + REALITY as of 2026-04.
XRAY_VERSION="${XRAY_VERSION:-v25.3.6}"

echo "Installing Xray-core (${XRAY_VERSION})..."
# --version pins the release; falls back to latest if the script does not
# recognise the flag (older install-release.sh versions).
if ! bash -c "$(curl -L https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install --version "${XRAY_VERSION}" -u root 2>/dev/null; then
    echo "Pinned install failed, falling back to latest stable..."
    bash -c "$(curl -L https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install -u root
fi

# Create config directory if it doesn't exist
mkdir -p /usr/local/etc/xray
mkdir -p /var/log/xray

# Copy template config
if [ -f "$(dirname "$0")/../config/xray_template.json" ]; then
    echo "Copying config template..."
    cp "$(dirname "$0")/../config/xray_template.json" /usr/local/etc/xray/config.json
else
    echo "WARNING: Template config not found, you'll need to create /usr/local/etc/xray/config.json manually"
fi

# Set permissions
chown -R root:root /usr/local/etc/xray
chown -R nobody:nogroup /var/log/xray
chmod 644 /usr/local/etc/xray/config.json

INSTALLED_VERSION="$(/usr/local/bin/xray version 2>/dev/null | head -1 || echo unknown)"

echo "=========================================="
echo "Xray installed successfully!"
echo "=========================================="
echo "Version:     ${INSTALLED_VERSION}"
echo "Config file: /usr/local/etc/xray/config.json"
echo "Binary:      /usr/local/bin/xray"
echo "Service:     xray.service"
echo ""
echo "Next steps:"
echo "1. Edit /usr/local/etc/xray/config.json and set REALITY keys"
echo "2. Start Xray: systemctl start xray"
echo "3. Enable autostart: systemctl enable xray"
echo "4. Check status: systemctl status xray"
echo "=========================================="
