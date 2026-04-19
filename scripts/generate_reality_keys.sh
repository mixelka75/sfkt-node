#!/bin/bash
# Generate REALITY keys for Xray
#
# Robust against both old and new xray x25519 output formats:
#   old: "Private key: XXX" / "Public key: XXX"
#   new: "PrivateKey: XXX" / "Password: XXX" (Password == public key)

set -e

TEMP_FILE="/tmp/xray_keys_$$.tmp"
trap 'rm -f "$TEMP_FILE"' EXIT

require() {
    if ! command -v "$1" &> /dev/null; then
        echo "Error: '$1' is required but not installed." >&2
        exit 1
    fi
}

require openssl

# Generate x25519 keypair via xray (preferred) or docker fallback.
generate_keys() {
    if command -v xray &> /dev/null; then
        xray x25519 > "$TEMP_FILE" 2>&1
    elif command -v docker &> /dev/null; then
        # teddysun/xray is a thin wrapper around the official binary and tracks upstream.
        docker run --rm teddysun/xray:latest xray x25519 > "$TEMP_FILE" 2>&1
    else
        echo "Error: Neither xray nor docker is installed" >&2
        echo "Install xray first: bash <(curl -L https://github.com/XTLS/Xray-install/raw/main/install-release.sh) @ install -u root" >&2
        exit 1
    fi
}

echo "Generating REALITY keys..."
generate_keys

# X25519 public/private keys are base64url, length 43 (unpadded) or 44 (padded with '=').
# grep -oE captures only the token on the key/password line.
# Xray v25.10+ uses "Password (PublicKey):" with a parenthesised suffix, so we
# allow any non-colon chars between the key name and the colon.
PRIVATE_KEY=$(grep -iE "^(privatekey|private key)[^:]*:" "$TEMP_FILE" | grep -oE '[A-Za-z0-9_=-]{43,44}' | head -1)
PUBLIC_KEY=$(grep -iE "^(password|publickey|public key)[^:]*:" "$TEMP_FILE" | grep -oE '[A-Za-z0-9_=-]{43,44}' | head -1)

# Short ID: 8 random bytes (16 hex chars). Acceptable shortId lengths in Xray are 0..16 hex chars.
SHORT_ID=$(openssl rand -hex 8)

if [ -z "$PRIVATE_KEY" ] || [ -z "$PUBLIC_KEY" ]; then
    echo "Error: Failed to extract keys from xray x25519 output" >&2
    echo "----- raw output -----" >&2
    cat "$TEMP_FILE" >&2
    echo "----------------------" >&2
    echo "Run manually: xray x25519" >&2
    exit 1
fi

echo ""
echo "======================================"
echo "REALITY Configuration Keys"
echo "======================================"
echo "Private Key: $PRIVATE_KEY"
echo "Public Key:  $PUBLIC_KEY"
echo "Short ID:    $SHORT_ID"
echo "======================================"
echo ""
echo "Save these values securely!"
echo "Private key goes in Xray config"
echo "Public key goes in client configs and database"
