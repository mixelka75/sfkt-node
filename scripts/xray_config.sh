#!/bin/bash
set -e

# SFKT Node - Xray Configuration Manager
# Manages Xray configuration using environment variables

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_DIR/.env"
XRAY_CONFIG="/usr/local/etc/xray/config.json"
XRAY_TEMPLATE="$PROJECT_DIR/config/xray_template.json"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
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
    echo -e "$1"
}

# Check if running as root
check_root() {
    if [ "$EUID" -ne 0 ]; then
        error "Please run as root (use sudo)"
    fi
}

# Load environment variables
load_env() {
    if [ ! -f "$ENV_FILE" ]; then
        error ".env file not found at $ENV_FILE"
    fi

    # Load .env file
    set -a
    source "$ENV_FILE"
    set +a

    # Check required variables
    if [ -z "$REALITY_PRIVATE_KEY" ] || [ "$REALITY_PRIVATE_KEY" = "your-private-key-here" ]; then
        error "REALITY_PRIVATE_KEY not set in .env file"
    fi

    if [ -z "$REALITY_SHORT_ID" ] || [ "$REALITY_SHORT_ID" = "your-short-id-here" ]; then
        error "REALITY_SHORT_ID not set in .env file"
    fi

    success "Loaded environment variables from .env"
}

# Pre-flight check: verify that NODE_SNI is reachable via TLS 1.3
# REALITY requires the dest to support TLS 1.3 + X25519, otherwise Xray will
# refuse to start.
preflight_sni() {
    local sni="${NODE_SNI:-max.ru}"
    local port="${SNI_PORT:-443}"

    info "Pre-flight: probing ${sni}:${port} for TLS 1.3..."

    if ! command -v curl &> /dev/null; then
        warning "curl not installed, skipping pre-flight probe"
        return 0
    fi

    # Try TLS 1.3 first. --tls-max 1.3 forces the minimum,
    # --tlsv1.3 enforces it as minimum too. We only care that handshake
    # succeeds and returns any HTTP response.
    local http_code
    http_code=$(curl -sk --max-time 8 --tlsv1.3 -o /dev/null -w "%{http_code}" "https://${sni}:${port}/" 2>/dev/null || echo "000")

    if [ "$http_code" = "000" ]; then
        warning "${sni}:${port} did not respond over TLS 1.3 from this host."
        warning "REALITY may fail to start. Consider changing NODE_SNI in .env to a"
        warning "domain that is reachable AND supports TLS 1.3 + X25519 from your VPS"
        warning "(e.g. www.yahoo.com, www.cloudflare.com, www.microsoft.com for non-RU hosts)."
    else
        success "${sni} reachable over TLS 1.3 (HTTP $http_code)"
    fi
}

# Update Xray configuration with values from .env
update_config() {
    info "Updating Xray configuration..."

    # Check if jq is installed
    if ! command -v jq &> /dev/null; then
        error "jq is required but not installed. Install with: apt-get install jq"
    fi

    # Check if template exists
    if [ ! -f "$XRAY_TEMPLATE" ]; then
        error "Template config not found at $XRAY_TEMPLATE"
    fi

    # Backup existing config
    if [ -f "$XRAY_CONFIG" ]; then
        cp "$XRAY_CONFIG" "$XRAY_CONFIG.backup.$(date +%Y%m%d_%H%M%S)"
        success "Backed up existing config"
    fi

    # Copy template to config location
    cp "$XRAY_TEMPLATE" "$XRAY_CONFIG"

    # Replace placeholders with actual values
    sed -i "s|PRIVATE_KEY_PLACEHOLDER|$REALITY_PRIVATE_KEY|g" "$XRAY_CONFIG"
    sed -i "s|SHORT_ID_PLACEHOLDER|$REALITY_SHORT_ID|g" "$XRAY_CONFIG"

    # Update SNI — must be a single eTLD+1. dest and serverNames MUST share the
    # same root; mixing unrelated domains breaks REALITY.
    if [ -n "$NODE_SNI" ]; then
        local temp_config
        temp_config=$(mktemp)
        jq --arg sni "$NODE_SNI" \
           '.inbounds[0].streamSettings.realitySettings.dest = ($sni + ":443") |
            .inbounds[0].streamSettings.realitySettings.serverNames = [$sni, ("www." + $sni)]' \
           "$XRAY_CONFIG" > "$temp_config"
        mv "$temp_config" "$XRAY_CONFIG"
        success "Updated SNI to $NODE_SNI (dest and serverNames)"
    fi

    # Update XHTTP path / mode / host from env (defaults preserved in template)
    local xhttp_path="${XHTTP_PATH:-/sfkt}"
    local xhttp_mode="${XRAY_MODE:-stream-one}"
    local xhttp_host="${XHTTP_HOST:-}"

    local temp_config
    temp_config=$(mktemp)
    jq --arg path "$xhttp_path" \
       --arg mode "$xhttp_mode" \
       --arg host "$xhttp_host" \
       '.inbounds[0].streamSettings.xhttpSettings.path = $path |
        .inbounds[0].streamSettings.xhttpSettings.mode = $mode |
        .inbounds[0].streamSettings.xhttpSettings.host = $host' \
       "$XRAY_CONFIG" > "$temp_config"
    mv "$temp_config" "$XRAY_CONFIG"
    success "Updated XHTTP: path=$xhttp_path, mode=$xhttp_mode, host='$xhttp_host'"

    # Update port if specified
    if [ -n "$NODE_PORT" ] && [ "$NODE_PORT" != "443" ]; then
        temp_config=$(mktemp)
        jq --arg port "$NODE_PORT" \
           '.inbounds[0].port = ($port | tonumber)' \
           "$XRAY_CONFIG" > "$temp_config"
        mv "$temp_config" "$XRAY_CONFIG"
        success "Updated port to $NODE_PORT"
    fi

    success "Updated Xray configuration"
}

# Validate Xray configuration
validate_config() {
    info "Validating Xray configuration..."

    if ! xray run -test -config "$XRAY_CONFIG" > /dev/null 2>&1; then
        info "Validation output:"
        xray run -test -config "$XRAY_CONFIG" 2>&1 | tail -20 || true
        error "Configuration validation failed! Run: xray run -test -config $XRAY_CONFIG"
    fi

    success "Configuration is valid"
}

# Reload Xray service
reload_xray() {
    info "Reloading Xray service..."

    if ! systemctl is-active --quiet xray; then
        warning "Xray service is not running, starting it..."
        systemctl start xray
    else
        # Xray service doesn't support reload, use restart instead
        warning "Restarting Xray (this will briefly interrupt connections)..."
        systemctl restart xray
    fi

    sleep 2

    if systemctl is-active --quiet xray; then
        success "Xray service is running"
    else
        info "Last 30 journal lines:"
        journalctl -u xray -n 30 --no-pager 2>&1 || true
        error "Xray service failed to start. Check: journalctl -u xray -n 50"
    fi

    # Ensure Xray actually listens on the configured port
    local port="${NODE_PORT:-443}"
    local attempts=0
    while [ $attempts -lt 10 ]; do
        if ss -tulpn 2>/dev/null | grep -q ":${port}.*xray"; then
            success "Xray listening on port ${port}"
            return 0
        fi
        attempts=$((attempts + 1))
        sleep 1
    done
    warning "Xray did not start listening on ${port} within 10s"
    journalctl -u xray -n 20 --no-pager 2>&1 || true
}

# Show current configuration status
show_status() {
    info "=== SFKT Xray Configuration Status ==="
    echo ""

    # Service status
    if systemctl is-active --quiet xray; then
        success "Xray service: Running"
    else
        error "Xray service: Not running"
    fi

    # Config file
    if [ -f "$XRAY_CONFIG" ]; then
        success "Config file: $XRAY_CONFIG"

        # Check if placeholders still exist
        if grep -q "PLACEHOLDER" "$XRAY_CONFIG"; then
            warning "Config contains PLACEHOLDER values - needs update"
        else
            success "Config has been configured (no placeholders)"
        fi
    else
        warning "Config file not found: $XRAY_CONFIG"
    fi

    # Environment variables
    if [ -f "$ENV_FILE" ]; then
        success ".env file: Found"
        echo ""
        info "Environment variables:"
        echo "  REALITY_PRIVATE_KEY: ${REALITY_PRIVATE_KEY:0:20}..."
        echo "  REALITY_PUBLIC_KEY: ${REALITY_PUBLIC_KEY:-not set}"
        echo "  REALITY_SHORT_ID: ${REALITY_SHORT_ID:-not set}"
        echo "  NODE_SNI: ${NODE_SNI:-max.ru}"
        echo "  NODE_PORT: ${NODE_PORT:-443}"
        echo "  XHTTP_PATH: ${XHTTP_PATH:-/sfkt}"
        echo "  XRAY_MODE: ${XRAY_MODE:-stream-one}"
    else
        warning ".env file not found"
    fi

    echo ""

    # Port check
    if ss -tulpn | grep -q ":${NODE_PORT:-443}.*xray"; then
        success "Xray is listening on port ${NODE_PORT:-443}"
    else
        warning "Xray is not listening on port ${NODE_PORT:-443}"
    fi

    echo ""
}

# Show configuration diff
show_diff() {
    if [ ! -f "$XRAY_CONFIG" ]; then
        error "Config file not found: $XRAY_CONFIG"
    fi

    info "Current configuration:"
    cat "$XRAY_CONFIG" | jq '.' 2>/dev/null || cat "$XRAY_CONFIG"
}

# Reset to template
reset_config() {
    info "Resetting configuration to template..."

    # Backup current config
    if [ -f "$XRAY_CONFIG" ]; then
        cp "$XRAY_CONFIG" "$XRAY_CONFIG.backup.$(date +%Y%m%d_%H%M%S)"
        success "Backed up current config"
    fi

    # Copy template
    cp "$XRAY_TEMPLATE" "$XRAY_CONFIG"
    success "Reset to template (don't forget to update with real keys!)"
}

# Update Xray binary to latest version
update_xray() {
    info "Updating Xray to latest version..."

    # Stop service
    if systemctl is-active --quiet xray; then
        systemctl stop xray
        success "Stopped Xray service"
    fi

    # Run installation script
    if [ -f "$SCRIPT_DIR/install_xray_host.sh" ]; then
        bash "$SCRIPT_DIR/install_xray_host.sh"
        success "Updated Xray binary"
    else
        error "install_xray_host.sh not found"
    fi

    # Start service
    systemctl start xray
    success "Started Xray service"
}

# Show help
show_help() {
    cat << EOF
SFKT Xray Configuration Manager

Usage: $0 <command>

Commands:
    update          Update Xray config with values from .env file
    validate        Validate current Xray configuration
    reload          Reload Xray service
    status          Show current configuration status
    show            Show current configuration (JSON)
    reset           Reset config to template (backup current)
    upgrade         Update Xray binary to latest version
    preflight       Probe NODE_SNI:443 for TLS 1.3 reachability
    apply           Preflight, update config, validate, and reload (recommended)
    help            Show this help message

Examples:
    # Apply configuration from .env and reload Xray
    sudo $0 apply

    # Check current status
    sudo $0 status

    # Validate configuration
    sudo $0 validate

    # Upgrade Xray to latest version
    sudo $0 upgrade

Environment variables (in .env file):
    REALITY_PRIVATE_KEY     Private key for REALITY protocol
    REALITY_PUBLIC_KEY      Public key (for clients)
    REALITY_SHORT_ID        Short ID for REALITY
    NODE_SNI                SNI for masquerading (default: max.ru)
    NODE_PORT               Port for Xray (default: 443)
    XHTTP_PATH              XHTTP path (default: /sfkt)
    XRAY_MODE               XHTTP mode (default: stream-one)
    XHTTP_HOST              XHTTP Host header (default: empty)

EOF
}

# Main command dispatcher
main() {
    local command="${1:-help}"

    case "$command" in
        update)
            check_root
            load_env
            update_config
            ;;
        validate)
            check_root
            validate_config
            ;;
        reload)
            check_root
            reload_xray
            ;;
        status)
            load_env || true
            show_status
            ;;
        show)
            show_diff
            ;;
        reset)
            check_root
            reset_config
            ;;
        upgrade)
            check_root
            update_xray
            ;;
        preflight)
            load_env
            preflight_sni
            ;;
        apply)
            check_root
            load_env
            preflight_sni
            update_config
            validate_config
            reload_xray
            success "Configuration applied successfully!"
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            error "Unknown command: $command\n\nRun '$0 help' for usage information"
            ;;
    esac
}

# Run main function
main "$@"
