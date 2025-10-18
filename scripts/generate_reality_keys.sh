#!/bin/bash
# Generate REALITY keys for Xray

# Check if xray is installed
if ! command -v xray &> /dev/null; then
    echo "Error: xray is not installed"
    exit 1
fi

# Generate keys
echo "Generating REALITY keys..."
KEYS=$(xray x25519)

PRIVATE_KEY=$(echo "$KEYS" | grep "Private key:" | awk '{print $3}')
PUBLIC_KEY=$(echo "$KEYS" | grep "Public key:" | awk '{print $3}')

# Generate short ID (random 8 characters)
SHORT_ID=$(openssl rand -hex 8)

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
