#!/bin/bash
#
# Rotary Phone VoIP Controller - Installation Script
#
# This script installs the rotary-phone service on a Raspberry Pi.
# Run as root: sudo ./install.sh
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

# Check if we're on a Raspberry Pi (optional, just warns)
if [[ ! -f /proc/device-tree/model ]] || ! grep -qi "raspberry" /proc/device-tree/model 2>/dev/null; then
    log_warn "This doesn't appear to be a Raspberry Pi. GPIO may not work correctly."
fi

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

log_info "Installing Rotary Phone VoIP Controller..."
log_info "Project directory: $PROJECT_DIR"
log_info "Install directory: $INSTALL_DIR"

# Install system dependencies
log_info "Installing system dependencies..."
apt-get update
apt-get install -y python3 python3-pip python3-venv alsa-utils

# Create installation directory
log_info "Creating installation directory..."
mkdir -p "$INSTALL_DIR"

# Copy project files
log_info "Copying project files..."
cp -r "$PROJECT_DIR/src" "$INSTALL_DIR/"
cp "$PROJECT_DIR/pyproject.toml" "$INSTALL_DIR/"
cp "$PROJECT_DIR/uv.lock" "$INSTALL_DIR/" 2>/dev/null || true

# Copy config file if it exists (don't overwrite existing config)
if [[ -f "$PROJECT_DIR/config.yaml" ]]; then
    if [[ ! -f "$INSTALL_DIR/config.yaml" ]]; then
        cp "$PROJECT_DIR/config.yaml" "$INSTALL_DIR/"
        log_info "Copied config.yaml to $INSTALL_DIR"
    else
        log_warn "config.yaml already exists at $INSTALL_DIR, not overwriting"
    fi
else
    log_warn "No config.yaml found in project. Create one at $INSTALL_DIR/config.yaml"
fi

# Install uv if not present
if ! command -v uv &> /dev/null; then
    log_info "Installing uv package manager..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

# Create virtual environment and install dependencies
log_info "Setting up Python virtual environment..."
cd "$INSTALL_DIR"
uv venv
uv sync

# Install systemd service
log_info "Installing systemd service..."
cp "$SCRIPT_DIR/rotary-phone.service" "$SERVICE_FILE"

# Reload systemd
log_info "Reloading systemd..."
systemctl daemon-reload

# Enable the service (but don't start it yet)
log_info "Enabling rotary-phone service..."
systemctl enable rotary-phone.service

echo ""
log_info "Installation complete!"
echo ""
echo "Next steps:"
echo "  1. Edit your configuration: sudo nano $INSTALL_DIR/config.yaml"
echo "  2. Start the service:       sudo systemctl start rotary-phone"
echo "  3. Check status:            sudo systemctl status rotary-phone"
echo "  4. View logs:               sudo journalctl -u rotary-phone -f"
echo ""
echo "Useful commands:"
echo "  sudo systemctl stop rotary-phone     # Stop the service"
echo "  sudo systemctl restart rotary-phone  # Restart the service"
echo "  sudo systemctl disable rotary-phone  # Disable auto-start"
echo ""
