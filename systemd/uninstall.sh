#!/bin/bash
#
# Rotary Phone VoIP Controller - Uninstallation Script
#
# This script removes the rotary-phone service from the system.
# Run as root: sudo ./uninstall.sh
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Installation directory
INSTALL_DIR="/opt/rotary-phone"
SERVICE_FILE="/etc/systemd/system/rotary-phone.service"

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
if [[ $EUID -ne 0 ]]; then
    log_error "This script must be run as root (use sudo)"
    exit 1
fi

log_info "Uninstalling Rotary Phone VoIP Controller..."

# Stop the service if running
if systemctl is-active --quiet rotary-phone.service 2>/dev/null; then
    log_info "Stopping rotary-phone service..."
    systemctl stop rotary-phone.service
fi

# Disable the service
if systemctl is-enabled --quiet rotary-phone.service 2>/dev/null; then
    log_info "Disabling rotary-phone service..."
    systemctl disable rotary-phone.service
fi

# Remove the service file
if [[ -f "$SERVICE_FILE" ]]; then
    log_info "Removing systemd service file..."
    rm "$SERVICE_FILE"
    systemctl daemon-reload
fi

# Ask about removing installation directory
if [[ -d "$INSTALL_DIR" ]]; then
    echo ""
    read -p "Remove installation directory $INSTALL_DIR? (y/N): " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        log_info "Removing installation directory..."
        rm -rf "$INSTALL_DIR"
    else
        log_warn "Keeping installation directory at $INSTALL_DIR"
        log_warn "Your config.yaml and logs are preserved."
    fi
fi

echo ""
log_info "Uninstallation complete!"
