#!/bin/bash
#
# Rotary Phone VoIP Controller - Installation Script
#
# Install directly from GitHub:
#   sudo bash -c "$(curl -fsSL https://raw.githubusercontent.com/jacob-meacham/rotary-voip/main/install.sh)"
#
# Or clone first and run locally:
#   git clone https://github.com/jacob-meacham/rotary-voip.git
#   cd rotary-voip
#   sudo ./install.sh
#
# To update after installation:
#   cd /opt/rotary-phone && sudo git pull && sudo .venv/bin/pip install .
#

set -e

# Configuration
REPO_URL="https://github.com/jacob-meacham/rotary-voip.git"
INSTALL_DIR="/opt/rotary-phone"
SERVICE_FILE="/etc/systemd/system/rotary-phone.service"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_step() {
    echo -e "${BLUE}==>${NC} $1"
}

# Check if running as root
if [[ $EUID -ne 0 ]]; then
    log_error "This script must be run as root (use sudo)"
    echo ""
    echo "Usage:"
    echo "  sudo ./install.sh"
    echo ""
    echo "Or install directly from GitHub:"
    echo "  sudo bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/jacob-meacham/rotary-voip/main/install.sh)\""
    exit 1
fi

# Check if we're on a Raspberry Pi (optional, just warns)
if [[ ! -f /proc/device-tree/model ]] || ! grep -qi "raspberry" /proc/device-tree/model 2>/dev/null; then
    log_warn "This doesn't appear to be a Raspberry Pi. GPIO may not work correctly."
fi

echo ""
echo -e "${GREEN}+------------------------------------------------------------+${NC}"
echo -e "${GREEN}|${NC}     Rotary Phone VoIP Controller - Installation Script     ${GREEN}|${NC}"
echo -e "${GREEN}+------------------------------------------------------------+${NC}"
echo ""

# Step 1: Install system dependencies
log_step "Installing system dependencies..."
apt-get update
apt-get install -y \
    python3 python3-pip python3-venv \
    alsa-utils \
    portaudio19-dev \
    hostapd dnsmasq \
    git

# Add user to required groups (for manual testing without service)
if [[ -n "$SUDO_USER" ]]; then
    log_info "Adding $SUDO_USER to gpio, audio, and dialout groups..."
    usermod -a -G gpio,audio,dialout "$SUDO_USER" 2>/dev/null || true
fi

# Step 2: Set up installation directory
log_step "Setting up installation directory..."

if [[ -d "$INSTALL_DIR/.git" ]]; then
    # Already a git repo - just pull latest
    log_info "Existing installation found, updating..."
    cd "$INSTALL_DIR"
    git pull
elif [[ -f "$(dirname "${BASH_SOURCE[0]}")/pyproject.toml" ]]; then
    # Running from within a local repo - copy it
    LOCAL_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    if [[ "$LOCAL_REPO" != "$INSTALL_DIR" ]]; then
        log_info "Copying local repository to $INSTALL_DIR..."
        rm -rf "$INSTALL_DIR"
        cp -r "$LOCAL_REPO" "$INSTALL_DIR"
    fi
else
    # Fresh install via curl - clone the repo
    log_info "Cloning repository to $INSTALL_DIR..."
    rm -rf "$INSTALL_DIR"
    git clone "$REPO_URL" "$INSTALL_DIR"
fi

# Create data directory (not tracked by git)
mkdir -p "$INSTALL_DIR/data"

# Step 3: Set up Python environment
log_step "Setting up Python environment..."

cd "$INSTALL_DIR"
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install .

# Step 4: Install systemd service
log_step "Installing systemd service..."
cp "$INSTALL_DIR/systemd/rotary-phone.service" "$SERVICE_FILE"

systemctl daemon-reload
systemctl enable rotary-phone.service
log_info "Service installed and enabled"

# Step 5: Install CLI tool
log_step "Installing CLI tool..."
ln -sf "$INSTALL_DIR/bin/rotary-voip" /usr/local/bin/rotary-voip
log_info "CLI installed: rotary-voip"

# Verification
echo ""
log_step "Verifying installation..."
VERIFY_PASSED=true

# Check required directories
for dir in "$INSTALL_DIR/src" "$INSTALL_DIR/sounds" "$INSTALL_DIR/data" "$INSTALL_DIR/.venv"; do
    if [[ -d "$dir" ]]; then
        echo -e "  ${GREEN}[OK]${NC} $dir"
    else
        echo -e "  ${RED}[X]${NC} $dir"
        VERIFY_PASSED=false
    fi
done

# Check required files
for file in "$INSTALL_DIR/pyproject.toml" "$INSTALL_DIR/config.yml.example"; do
    if [[ -f "$file" ]]; then
        echo -e "  ${GREEN}[OK]${NC} $file"
    else
        echo -e "  ${RED}[X]${NC} $file"
        VERIFY_PASSED=false
    fi
done

# Check config file
if [[ -f "$INSTALL_DIR/config.yml" ]] || [[ -f "$INSTALL_DIR/config.yaml" ]]; then
    echo -e "  ${GREEN}[OK]${NC} Configuration file found"
else
    echo -e "  ${YELLOW}[!]${NC} No config.yml - copy from config.yml.example"
fi

# Check systemd service
if systemctl is-enabled rotary-phone.service &>/dev/null; then
    echo -e "  ${GREEN}[OK]${NC} Service enabled"
else
    echo -e "  ${YELLOW}[!]${NC} Service not enabled"
fi

echo ""
if [[ "$VERIFY_PASSED" == "true" ]]; then
    echo -e "${GREEN}+------------------------------------------------------------+${NC}"
    echo -e "${GREEN}|${NC}              Installation complete!                         ${GREEN}|${NC}"
    echo -e "${GREEN}+------------------------------------------------------------+${NC}"
else
    log_error "Installation completed with errors - check above"
fi

echo ""
echo "Next steps:"
echo "  1. Edit your configuration:"
echo "     sudo rotary-voip config"
echo ""
echo "  2. Start the service:"
echo "     sudo rotary-voip start"
echo ""
echo "  3. View logs:"
echo "     sudo rotary-voip logs"
echo ""
echo "CLI commands:"
echo "  sudo rotary-voip update        # Update to latest version"
echo "  sudo rotary-voip status        # Show service status"
echo "  sudo rotary-voip restart       # Restart the service"
echo "  sudo rotary-voip manage-users  # Manage web admin users"
echo "  rotary-voip help               # Show all commands"
echo ""
if [[ -n "$SUDO_USER" ]]; then
    echo -e "${YELLOW}Note:${NC} Log out and back in for group changes to take effect (gpio, audio, dialout)"
    echo ""
fi
