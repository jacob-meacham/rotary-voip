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
apt-get install -y \
    python3 python3-pip python3-venv \
    alsa-utils \
    portaudio19-dev \
    hostapd dnsmasq \
    curl git

# Add user to required groups (for manual testing without service)
if [[ -n "$SUDO_USER" ]]; then
    log_info "Adding $SUDO_USER to gpio, audio, and dialout groups..."
    usermod -a -G gpio,audio,dialout "$SUDO_USER" 2>/dev/null || true
fi

# Create installation directory
log_info "Creating installation directory..."
mkdir -p "$INSTALL_DIR"

# Copy project files
log_info "Copying project files..."
cp -r "$PROJECT_DIR/src" "$INSTALL_DIR/"
cp "$PROJECT_DIR/pyproject.toml" "$INSTALL_DIR/"
cp "$PROJECT_DIR/uv.lock" "$INSTALL_DIR/" 2>/dev/null || true

# Copy sounds directory
if [[ -d "$PROJECT_DIR/sounds" ]]; then
    cp -r "$PROJECT_DIR/sounds" "$INSTALL_DIR/"
    log_info "Copied sounds/ to $INSTALL_DIR"
fi

# Create data directory for database
mkdir -p "$INSTALL_DIR/data"
log_info "Created data/ directory"

# Copy example config (always update it)
if [[ -f "$PROJECT_DIR/config.yml.example" ]]; then
    cp "$PROJECT_DIR/config.yml.example" "$INSTALL_DIR/"
    log_info "Copied config.yml.example to $INSTALL_DIR"
fi

# Copy config file if it exists (don't overwrite existing config)
# Check for both .yaml and .yml extensions
CONFIG_SRC=""
if [[ -f "$PROJECT_DIR/config.yaml" ]]; then
    CONFIG_SRC="$PROJECT_DIR/config.yaml"
elif [[ -f "$PROJECT_DIR/config.yml" ]]; then
    CONFIG_SRC="$PROJECT_DIR/config.yml"
fi

if [[ -n "$CONFIG_SRC" ]]; then
    if [[ ! -f "$INSTALL_DIR/config.yaml" && ! -f "$INSTALL_DIR/config.yml" ]]; then
        cp "$CONFIG_SRC" "$INSTALL_DIR/config.yml"
        log_info "Copied config to $INSTALL_DIR/config.yml"
    else
        log_warn "config.yml already exists at $INSTALL_DIR, not overwriting"
    fi
else
    log_warn "No config.yaml/config.yml found in project."
    log_warn "Copy config.yml.example to config.yml and edit it with your settings."
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

# Verify installation
echo ""
log_info "Verifying installation..."
VERIFY_PASSED=true

# Check required directories
for dir in "$INSTALL_DIR/src" "$INSTALL_DIR/sounds" "$INSTALL_DIR/data" "$INSTALL_DIR/.venv"; do
    if [[ -d "$dir" ]]; then
        echo -e "  ${GREEN}[OK]${NC} $dir"
    else
        echo -e "  ${RED}[MISSING]${NC} $dir"
        VERIFY_PASSED=false
    fi
done

# Check required files
for file in "$INSTALL_DIR/pyproject.toml" "$INSTALL_DIR/config.yml.example"; do
    if [[ -f "$file" ]]; then
        echo -e "  ${GREEN}[OK]${NC} $file"
    else
        echo -e "  ${RED}[MISSING]${NC} $file"
        VERIFY_PASSED=false
    fi
done

# Check config file
if [[ -f "$INSTALL_DIR/config.yml" ]] || [[ -f "$INSTALL_DIR/config.yaml" ]]; then
    echo -e "  ${GREEN}[OK]${NC} Configuration file found"
else
    echo -e "  ${YELLOW}[WARN]${NC} No config.yml - copy from config.yml.example"
fi

# Check systemd service
if systemctl is-enabled rotary-phone.service &>/dev/null; then
    echo -e "  ${GREEN}[OK]${NC} Service enabled"
else
    echo -e "  ${YELLOW}[WARN]${NC} Service not enabled"
fi

echo ""
if [[ "$VERIFY_PASSED" == "true" ]]; then
    log_info "Installation complete!"
else
    log_error "Installation completed with errors - check above"
fi

echo ""
echo "Next steps:"
echo "  1. Edit your configuration: sudo nano $INSTALL_DIR/config.yml"
echo "  2. Start the service:       sudo systemctl start rotary-phone"
echo "  3. Check status:            sudo systemctl status rotary-phone"
echo "  4. View logs:               sudo journalctl -u rotary-phone -f"
echo ""
echo "Useful commands:"
echo "  sudo systemctl stop rotary-phone     # Stop the service"
echo "  sudo systemctl restart rotary-phone  # Restart the service"
echo "  sudo systemctl disable rotary-phone  # Disable auto-start"
echo ""
if [[ -n "$SUDO_USER" ]]; then
    echo "Note: Log out and back in for group changes to take effect (gpio, audio, dialout)"
fi
echo ""
