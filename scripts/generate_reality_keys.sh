#!/bin/bash
# Generate REALITY keys for Xray

set -e

# Temp file for xray output
TEMP_FILE="/tmp/xray_keys_$$.tmp"

# Function to generate keys using xray
generate_keys() {
    if command -v xray &> /dev/null; then
        # xray is installed locally
        xray x25519 > "$TEMP_FILE" 2>&1
    elif command -v docker &> /dev/null; then
        # Use Docker to run xray
        docker run --rm teddysun/xray:latest xray x25519 > "$TEMP_FILE" 2>&1
    else
        echo "Error: Neither xray nor docker is installed"
        echo "Please install docker or xray to generate REALITY keys"
        exit 1
    fi
}

# Generate keys
echo "Generating REALITY keys..."
generate_keys

# Extract keys using multiple patterns (different xray versions output different formats)
# Try pattern 1: "Private key: xxx"
PRIVATE_KEY=$(grep -iE "(private|privatekey)" "$TEMP_FILE" | grep -oE '[A-Za-z0-9_-]{43,44}' | head -1)

# Try pattern 2: "Public key: xxx" or "Password: xxx"
PUBLIC_KEY=$(grep -iE "(public|password)" "$TEMP_FILE" | grep -oE '[A-Za-z0-9_-]{43,44}' | head -1)

# Generate short ID (random 16 hex characters = 8 bytes)
SHORT_ID=$(openssl rand -hex 8)

# Clean up temp file
rm -f "$TEMP_FILE"

# Validate keys were extracted
if [ -z "$PRIVATE_KEY" ] || [ -z "$PUBLIC_KEY" ]; then
    echo "Error: Failed to extract keys from xray output"
    echo "Please run manually: xray x25519"
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
