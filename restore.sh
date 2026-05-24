#!/bin/bash
#
# Rotary Phone VoIP Controller - Restore Script
#
# Restores non-git assets (config, credentials, database, custom sounds,
# call recordings) from a backup directory into the installed location.
#
# Usage:
#   sudo ./restore.sh BACKUP_DIR
#
# BACKUP_DIR should point to a saved copy of the rotary-phone project
# directory (the one that contains config.yml, data/, sounds/, etc.).
#
# Idempotent: re-running overwrites destination files with backup versions.
#

set -e

INSTALL_DIR="/opt/rotary-phone"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step() { echo -e "${BLUE}==>${NC} $1"; }

if [[ $EUID -ne 0 ]]; then
    log_error "This script must be run as root (use sudo)"
    exit 1
fi

if [[ $# -ne 1 ]]; then
    log_error "Usage: sudo $0 BACKUP_DIR"
    echo ""
    echo "BACKUP_DIR is the path to a saved rotary-phone project directory."
    echo "Example: sudo $0 /tmp/rotary-recovery/rotary-phone"
    exit 1
fi

BACKUP_DIR="$1"

if [[ ! -d "$BACKUP_DIR" ]]; then
    log_error "Backup directory does not exist: $BACKUP_DIR"
    exit 1
fi

if [[ ! -d "$INSTALL_DIR" ]]; then
    log_error "Install directory does not exist: $INSTALL_DIR"
    log_error "Run install.sh first."
    exit 1
fi

echo ""
echo -e "${GREEN}+------------------------------------------------------------+${NC}"
echo -e "${GREEN}|${NC}    Rotary Phone VoIP Controller - Restore from Backup      ${GREEN}|${NC}"
echo -e "${GREEN}+------------------------------------------------------------+${NC}"
echo ""
log_info "Source: $BACKUP_DIR"
log_info "Target: $INSTALL_DIR"
echo ""

# Helper: copy a file if it exists in the backup
restore_file() {
    local rel_path="$1"
    local src="$BACKUP_DIR/$rel_path"
    local dst="$INSTALL_DIR/$rel_path"
    if [[ -f "$src" ]]; then
        mkdir -p "$(dirname "$dst")"
        cp -p "$src" "$dst"
        log_info "Restored $rel_path"
    fi
}

# Helper: copy all matching files from a backup subdir
restore_glob() {
    local rel_dir="$1"
    local pattern="$2"
    local src_dir="$BACKUP_DIR/$rel_dir"
    local dst_dir="$INSTALL_DIR/$rel_dir"
    if [[ -d "$src_dir" ]]; then
        mkdir -p "$dst_dir"
        local count=0
        shopt -s nullglob
        for f in "$src_dir"/$pattern; do
            cp -p "$f" "$dst_dir/"
            count=$((count + 1))
        done
        shopt -u nullglob
        [[ $count -gt 0 ]] && log_info "Restored $count file(s) to $rel_dir/ matching $pattern"
    fi
}

# 1. Core config files (gitignored)
log_step "Restoring config files..."
restore_file "config.yml"
restore_file ".env"
for f in "$BACKUP_DIR"/.env.*; do
    [[ -f "$f" ]] || continue
    name=$(basename "$f")
    cp -p "$f" "$INSTALL_DIR/$name"
    log_info "Restored $name"
done

# 2. Call history database and any other DBs
log_step "Restoring database..."
restore_glob "data" "*.db"
restore_glob "data" "*.sqlite"
restore_glob "data" "*.sqlite3"

# 3. Custom sounds (ring tones, dial tones, etc.)
log_step "Restoring custom sounds..."
restore_glob "sounds" "*.wav"
restore_glob "sounds" "*.mp3"

# 4. Call recordings in project root
log_step "Restoring call recordings..."
restore_glob "" "call_recording_*.wav"
restore_glob "" "call_recording_*.bin"

# 5. Test/diagnostic audio files
restore_glob "" "test-mic*.wav"

# Set ownership to root (matches install.sh's clone-as-root behavior)
log_step "Setting ownership..."
chown -R root:root "$INSTALL_DIR"

# Restrict permissions on credential files
chmod 600 "$INSTALL_DIR/config.yml" 2>/dev/null || true
chmod 600 "$INSTALL_DIR"/.env* 2>/dev/null || true

# Restart service if it's installed and was running
if systemctl list-unit-files | grep -q '^rotary-phone\.service'; then
    log_step "Restarting rotary-phone service..."
    systemctl restart rotary-phone.service || log_warn "Service restart failed (check: sudo journalctl -u rotary-phone -n 30)"
fi

echo ""
echo -e "${GREEN}+------------------------------------------------------------+${NC}"
echo -e "${GREEN}|${NC}                  Restore complete!                          ${GREEN}|${NC}"
echo -e "${GREEN}+------------------------------------------------------------+${NC}"
echo ""
echo "Verify with:"
echo "  sudo rotary-voip status"
echo "  sudo rotary-voip logs"
