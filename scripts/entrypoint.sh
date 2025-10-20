#!/bin/bash
set -e

echo "=========================================="
echo "SFKT Node Entrypoint"
echo "=========================================="

# Check required environment variables
if [ -z "$REALITY_PRIVATE_KEY" ]; then
    echo "ERROR: REALITY_PRIVATE_KEY is not set!"
    exit 1
fi

if [ -z "$REALITY_SHORT_ID" ]; then
    echo "ERROR: REALITY_SHORT_ID is not set!"
    exit 1
fi

echo "Node: $NODE_NAME"
echo "Hostname: $NODE_HOSTNAME"
echo "Location: $NODE_COUNTRY, $NODE_CITY"
echo "=========================================="

# Replace placeholders in Xray config
echo "Configuring Xray..."
sed -i "s/PRIVATE_KEY_PLACEHOLDER/$REALITY_PRIVATE_KEY/g" /etc/xray/config.json
sed -i "s/SHORT_ID_PLACEHOLDER/$REALITY_SHORT_ID/g" /etc/xray/config.json

# Replace SNI if provided
if [ -n "$NODE_SNI" ]; then
    echo "Setting SNI to: $NODE_SNI"
    sed -i "s/\"dest\": \"vk.com:443\"/\"dest\": \"$NODE_SNI:443\"/g" /etc/xray/config.json
fi

# Validate Xray config
echo "Validating Xray configuration..."
if ! /usr/local/bin/xray test -config /etc/xray/config.json; then
    echo "ERROR: Xray configuration validation failed!"
    echo "Config contents:"
    cat /etc/xray/config.json
    exit 1
fi

echo "Xray configuration is valid"
echo "=========================================="
echo "Starting services..."
echo "=========================================="

# Start supervisor
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
