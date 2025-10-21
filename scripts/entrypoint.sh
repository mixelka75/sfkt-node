#!/bin/bash
set -e

# SFKT Node Agent - Docker Entrypoint
# This script runs inside the node-agent container

echo "=========================================="
echo "SFKT Node Agent Starting"
echo "=========================================="

# Check required environment variables
if [ -z "$NODE_API_KEY" ]; then
    echo "ERROR: NODE_API_KEY not set"
    exit 1
fi

if [ -z "$MAIN_SERVER_URL" ]; then
    echo "ERROR: MAIN_SERVER_URL not set"
    exit 1
fi

echo "Configuration:"
echo "  Main Server: $MAIN_SERVER_URL"
echo "  Node Name: ${NODE_NAME:-Not set}"
echo "  Node ID: ${NODE_ID:-Will register}"
echo "  Inbound Tag: ${INBOUND_TAG:-vless-in}"
echo "  Sync Interval: ${SYNC_INTERVAL:-30}s"
echo "=========================================="

# Wait for Xray to be ready on host
echo "Waiting for Xray service on host..."
MAX_RETRIES=30
RETRY_COUNT=0

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    # Check if Xray config exists (mounted from host)
    if [ -f "/usr/local/etc/xray/config.json" ]; then
        echo "✓ Xray config found"
        break
    fi

    RETRY_COUNT=$((RETRY_COUNT + 1))
    echo "Waiting for Xray config... ($RETRY_COUNT/$MAX_RETRIES)"
    sleep 2
done

if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
    echo "ERROR: Xray config not found after $MAX_RETRIES attempts"
    echo "Make sure Xray is installed on the host and config exists at /usr/local/etc/xray/config.json"
    exit 1
fi

# Check if Xray is listening on stats API port
echo "Checking Xray stats API..."
RETRY_COUNT=0
while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    # Use netstat or ss to check if port 10085 is listening
    if ss -tulpn 2>/dev/null | grep -q ":10085" || netstat -tuln 2>/dev/null | grep -q ":10085"; then
        echo "✓ Xray stats API is ready on port 10085"
        break
    fi

    RETRY_COUNT=$((RETRY_COUNT + 1))
    echo "Waiting for Xray stats API... ($RETRY_COUNT/$MAX_RETRIES)"
    sleep 2
done

if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
    echo "WARNING: Xray stats API not detected on port 10085"
    echo "Node agent will start but stats collection may fail"
    echo "Make sure Xray service is running: systemctl status xray"
fi

echo "=========================================="
echo "Starting node agent..."
echo "=========================================="

# Start node agent
exec python3 /app/node_agent.py
