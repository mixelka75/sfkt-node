#!/bin/bash
set -e

# SFKT Node - Automated Installation Script
# This script will install and configure a SFKT VPN node

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
error() {
    echo -e "${RED}ERROR: $1${NC}" >&2
    exit 1
}

success() {
    echo -e "${GREEN}✓ $1${NC}"
}

warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

# Banner
echo -e "${BLUE}"
cat << "EOF"
╔═══════════════════════════════════════╗
║     SFKT VPN Node Installation       ║
║     Automated Setup Script            ║
╚═══════════════════════════════════════╝
EOF
echo -e "${NC}"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    error "Please run as root (use sudo)"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Step 1: System checks
info "Step 1/8: Checking system requirements..."

# Check OS
if ! command -v lsb_release &> /dev/null; then
    apt-get update -qq && apt-get install -y lsb-release
fi

OS_NAME=$(lsb_release -si)
OS_VERSION=$(lsb_release -sr)

if [[ "$OS_NAME" != "Ubuntu" && "$OS_NAME" != "Debian" ]]; then
    error "This script only supports Ubuntu and Debian"
fi

success "OS: $OS_NAME $OS_VERSION"

# Step 2: Install dependencies
info "Step 2/8: Installing system dependencies..."

apt-get update -qq
apt-get install -y curl wget git jq openssl net-tools iptables ca-certificates gnupg lsb-release

success "System dependencies installed"

# Step 3: Install Docker
info "Step 3/8: Installing Docker..."

if command -v docker &> /dev/null; then
    success "Docker already installed: $(docker --version)"
else
    curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
    sh /tmp/get-docker.sh
    rm /tmp/get-docker.sh
    success "Docker installed: $(docker --version)"
fi

# Install Docker Compose
if command -v docker compose &> /dev/null; then
    success "Docker Compose already installed"
else
    COMPOSE_VERSION=$(curl -s https://api.github.com/repos/docker/compose/releases/latest | grep 'tag_name' | cut -d\" -f4)
    curl -L "https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose
    success "Docker Compose installed: $(docker compose version)"
fi

# Step 4: Install Xray on host
info "Step 4/8: Installing Xray on host system..."

if [ -f "$SCRIPT_DIR/install_xray_host.sh" ]; then
    bash "$SCRIPT_DIR/install_xray_host.sh"
    success "Xray installed on host"
else
    warning "install_xray_host.sh not found, skipping Xray installation"
fi

# Step 5: Generate REALITY keys
info "Step 5/8: Generating REALITY keys..."

echo ""
info "Generating X25519 key pair for REALITY protocol..."

# Generate keys using Docker
TEMP_KEY_FILE="/tmp/sfkt_reality_keys_$$.tmp"

# Run xray x25519 command
if command -v xray &> /dev/null; then
    # Use local xray if available
    xray x25519 > "$TEMP_KEY_FILE" 2>&1
else
    # Use Docker
    docker run --rm teddysun/xray:latest xray x25519 > "$TEMP_KEY_FILE" 2>&1
fi

# Extract keys from output
# xray x25519 outputs: PrivateKey: xxx, Password: xxx (Password is the public key)
REALITY_PRIVATE=$(grep -iE "(privatekey|private key)" "$TEMP_KEY_FILE" | grep -oE '[A-Za-z0-9_-]{43,44}' | head -1)
REALITY_PUBLIC=$(grep -iE "(password|publickey|public key)" "$TEMP_KEY_FILE" | grep -oE '[A-Za-z0-9_-]{43,44}' | head -1)

# Generate Short ID separately
REALITY_SHORT=$(openssl rand -hex 8)

rm -f "$TEMP_KEY_FILE"

# Validate keys
if [ -z "$REALITY_PRIVATE" ] || [ -z "$REALITY_PUBLIC" ] || [ -z "$REALITY_SHORT" ]; then
    error "Failed to generate REALITY keys. Please run 'xray x25519' manually."
fi

echo ""
success "REALITY keys generated successfully"
echo -e "${YELLOW}═══════════════════════════════════════${NC}"
echo -e "${GREEN}Private Key:${NC} $REALITY_PRIVATE"
echo -e "${GREEN}Public Key:${NC}  $REALITY_PUBLIC"
echo -e "${GREEN}Short ID:${NC}    $REALITY_SHORT"
echo -e "${YELLOW}═══════════════════════════════════════${NC}"
echo ""

# Step 6: Collect configuration
info "Step 6/8: Collecting node configuration..."

echo ""
echo -e "${BLUE}Please provide the following information:${NC}"
echo ""

# Node name
read -p "Node name (e.g., Moscow-1): " NODE_NAME
if [ -z "$NODE_NAME" ]; then
    error "Node name is required"
fi

# IP address
DEFAULT_IP=$(curl -s ifconfig.me || curl -s icanhazip.com || echo "")
read -p "Node IP address [$DEFAULT_IP]: " NODE_IP
NODE_IP=${NODE_IP:-$DEFAULT_IP}

if [ -z "$NODE_IP" ]; then
    error "Node IP is required"
fi

# Hostname (default to IP)
read -p "Node hostname [$NODE_IP]: " NODE_HOSTNAME
NODE_HOSTNAME=${NODE_HOSTNAME:-$NODE_IP}

# Port
read -p "VPN port [443]: " NODE_PORT
NODE_PORT=${NODE_PORT:-443}

# Country
read -p "Country (e.g., Russia): " NODE_COUNTRY
if [ -z "$NODE_COUNTRY" ]; then
    error "Country is required"
fi

# Country code
read -p "Country code (e.g., RU): " NODE_COUNTRY_CODE
NODE_COUNTRY_CODE=$(echo "$NODE_COUNTRY_CODE" | tr '[:lower:]' '[:upper:]')
if [ -z "$NODE_COUNTRY_CODE" ]; then
    error "Country code is required"
fi

# City
read -p "City (e.g., Moscow): " NODE_CITY
if [ -z "$NODE_CITY" ]; then
    error "City is required"
fi

# SNI
read -p "SNI for masquerading [max.ru]: " NODE_SNI
NODE_SNI=${NODE_SNI:-max.ru}

# Main server URL
read -p "Main server URL [https://sfkt.mxl.wtf]: " MAIN_SERVER_URL
MAIN_SERVER_URL=${MAIN_SERVER_URL:-https://sfkt.mxl.wtf}

# Node API key
read -p "Node API key (from main server): " NODE_API_KEY
if [ -z "$NODE_API_KEY" ]; then
    error "Node API key is required"
fi

# Step 7: Create configuration
info "Step 7/8: Creating configuration files..."

cd "$PROJECT_DIR"

# Create .env file
cat > .env << EOF
# ========================================
# Node Information
# ========================================
NODE_NAME=$NODE_NAME
NODE_HOSTNAME=$NODE_HOSTNAME
NODE_IP=$NODE_IP
NODE_PORT=$NODE_PORT

# ========================================
# Location
# ========================================
NODE_COUNTRY=$NODE_COUNTRY
NODE_COUNTRY_CODE=$NODE_COUNTRY_CODE
NODE_CITY=$NODE_CITY

# ========================================
# REALITY Keys
# ========================================
REALITY_PRIVATE_KEY=$REALITY_PRIVATE
REALITY_PUBLIC_KEY=$REALITY_PUBLIC
REALITY_SHORT_ID=$REALITY_SHORT

# ========================================
# SNI Masking
# ========================================
NODE_SNI=$NODE_SNI

# ========================================
# Main Server Connection
# ========================================
MAIN_SERVER_URL=$MAIN_SERVER_URL
NODE_API_KEY=$NODE_API_KEY

# ========================================
# Sync Intervals (seconds)
# ========================================
SYNC_INTERVAL=30
HEALTH_CHECK_INTERVAL=60
USER_SYNC_INTERVAL=60

# ========================================
# Xray Configuration
# ========================================
INBOUND_TAG=vless-in
EOF

success ".env file created"

# Create docker-compose.yml if it doesn't exist
if [ ! -f "docker-compose.yml" ] && [ -f "docker-compose.example.yml" ]; then
    cp docker-compose.example.yml docker-compose.yml
    success "docker-compose.yml created"
fi

# Step 8: Configure Xray
info "Step 8/8: Configuring Xray..."

# Apply Xray configuration
if [ -f "$SCRIPT_DIR/xray_config.sh" ]; then
    bash "$SCRIPT_DIR/xray_config.sh" apply
    success "Xray configured"
else
    warning "xray_config.sh not found, manual Xray configuration required"
fi

# Configure network
info "Configuring network settings..."

# Enable IP forwarding
sysctl -w net.ipv4.ip_forward=1 > /dev/null
echo "net.ipv4.ip_forward=1" >> /etc/sysctl.conf

# Configure iptables
iptables -P FORWARD ACCEPT
iptables -t nat -C POSTROUTING -o eth0 -j MASQUERADE 2>/dev/null || \
    iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE

# Try to save iptables rules
netfilter-persistent save 2>/dev/null || iptables-save > /etc/iptables/rules.v4 2>/dev/null || true

success "Network configured"

# Create Docker network
docker network create sfkt_network 2>/dev/null || true
success "Docker network ready"

# Start services
info "Starting node services..."

cd "$PROJECT_DIR"
docker compose down 2>/dev/null || true
docker compose up -d --build

success "Services started"

# Wait for services to be ready
info "Waiting for services to initialize..."
sleep 5

# Check status
if docker compose ps | grep -q "Up"; then
    success "Node agent is running"
else
    error "Node agent failed to start. Check logs: docker compose logs"
fi

# Final output
echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}         SFKT VPN Node Installation Complete!              ${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${BLUE}Node Information:${NC}"
echo -e "  Name:        $NODE_NAME"
echo -e "  IP:          $NODE_IP"
echo -e "  Port:        $NODE_PORT"
echo -e "  Location:    $NODE_CITY, $NODE_COUNTRY ($NODE_COUNTRY_CODE)"
echo ""
echo -e "${BLUE}REALITY Configuration:${NC}"
echo -e "  Private Key: $REALITY_PRIVATE"
echo -e "  Public Key:  $REALITY_PUBLIC"
echo -e "  Short ID:    $REALITY_SHORT"
echo ""
echo -e "${YELLOW}⚠  IMPORTANT: Save the Public Key and Short ID!${NC}"
echo -e "${YELLOW}   You need to add them to the main server database.${NC}"
echo ""
echo -e "${BLUE}Useful Commands:${NC}"
echo -e "  View logs:          ${GREEN}docker compose logs -f${NC}"
echo -e "  Check status:       ${GREEN}docker compose ps${NC}"
echo -e "  Restart services:   ${GREEN}docker compose restart${NC}"
echo -e "  Update node:        ${GREEN}git pull && docker compose up -d --build${NC}"
echo ""
echo -e "${BLUE}Next Steps:${NC}"
echo -e "  1. Add the Public Key and Short ID to the main server database"
echo -e "  2. Check logs to verify node registration: ${GREEN}docker compose logs -f${NC}"
echo -e "  3. Test VPN connection from client"
echo ""
echo -e "${GREEN}Installation completed successfully!${NC}"
echo ""
