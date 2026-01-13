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
echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║${NC}     Rotary Phone VoIP Controller - Installation Script     ${GREEN}║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Determine if we're running from within the repo or via curl
PROJECT_DIR=""
TEMP_CLONE=""

if [[ -f "$(dirname "${BASH_SOURCE[0]}")/pyproject.toml" ]]; then
    # Running from within the repo
    PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    log_info "Running from local repository: $PROJECT_DIR"
elif [[ -f "./pyproject.toml" ]]; then
    # Running from repo root
    PROJECT_DIR="$(pwd)"
    log_info "Running from local repository: $PROJECT_DIR"
else
    # Running via curl - need to clone the repo first
    log_step "Cloning repository from GitHub..."

    # Install git if not present
    if ! command -v git &> /dev/null; then
        log_info "Installing git..."
        apt-get update -qq
        apt-get install -y -qq git
    fi

    TEMP_CLONE=$(mktemp -d)
    git clone --depth 1 "$REPO_URL" "$TEMP_CLONE"
    PROJECT_DIR="$TEMP_CLONE"
    log_info "Cloned to temporary directory: $PROJECT_DIR"
fi

log_info "Install directory: $INSTALL_DIR"
echo ""

# Step 1: Install system dependencies
log_step "Installing system dependencies..."
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

# Step 2: Create installation directory and copy files
log_step "Setting up installation directory..."
mkdir -p "$INSTALL_DIR"

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
fi

# Step 3: Install uv and Python dependencies
log_step "Setting up Python environment..."

if ! command -v uv &> /dev/null; then
    log_info "Installing uv package manager..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="/root/.local/bin:$PATH"
fi

cd "$INSTALL_DIR"
uv venv
uv sync

# Step 4: Install systemd service
log_step "Installing systemd service..."
cp "$PROJECT_DIR/systemd/rotary-phone.service" "$SERVICE_FILE"

systemctl daemon-reload
systemctl enable rotary-phone.service
log_info "Service installed and enabled"

# Cleanup temp clone if used
if [[ -n "$TEMP_CLONE" && -d "$TEMP_CLONE" ]]; then
    rm -rf "$TEMP_CLONE"
    log_info "Cleaned up temporary files"
fi

# Verification
echo ""
log_step "Verifying installation..."
VERIFY_PASSED=true

# Check required directories
for dir in "$INSTALL_DIR/src" "$INSTALL_DIR/sounds" "$INSTALL_DIR/data" "$INSTALL_DIR/.venv"; do
    if [[ -d "$dir" ]]; then
        echo -e "  ${GREEN}✓${NC} $dir"
    else
        echo -e "  ${RED}✗${NC} $dir"
        VERIFY_PASSED=false
    fi
done

# Check required files
for file in "$INSTALL_DIR/pyproject.toml" "$INSTALL_DIR/config.yml.example"; do
    if [[ -f "$file" ]]; then
        echo -e "  ${GREEN}✓${NC} $file"
    else
        echo -e "  ${RED}✗${NC} $file"
        VERIFY_PASSED=false
    fi
done

# Check config file
if [[ -f "$INSTALL_DIR/config.yml" ]] || [[ -f "$INSTALL_DIR/config.yaml" ]]; then
    echo -e "  ${GREEN}✓${NC} Configuration file found"
else
    echo -e "  ${YELLOW}!${NC} No config.yml - copy from config.yml.example"
fi

# Check systemd service
if systemctl is-enabled rotary-phone.service &>/dev/null; then
    echo -e "  ${GREEN}✓${NC} Service enabled"
else
    echo -e "  ${YELLOW}!${NC} Service not enabled"
fi

echo ""
if [[ "$VERIFY_PASSED" == "true" ]]; then
    echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║${NC}              Installation complete!                         ${GREEN}║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
else
    log_error "Installation completed with errors - check above"
fi

echo ""
echo "Next steps:"
echo "  1. Edit your configuration:"
echo "     sudo nano $INSTALL_DIR/config.yml"
echo ""
echo "  2. Start the service:"
echo "     sudo systemctl start rotary-phone"
echo ""
echo "  3. Check status:"
echo "     sudo systemctl status rotary-phone"
echo ""
echo "  4. View logs:"
echo "     sudo journalctl -u rotary-phone -f"
echo ""
echo "Useful commands:"
echo "  sudo systemctl stop rotary-phone     # Stop the service"
echo "  sudo systemctl restart rotary-phone  # Restart the service"
echo "  sudo systemctl disable rotary-phone  # Disable auto-start"
echo ""
if [[ -n "$SUDO_USER" ]]; then
    echo -e "${YELLOW}Note:${NC} Log out and back in for group changes to take effect (gpio, audio, dialout)"
    echo ""
fi
