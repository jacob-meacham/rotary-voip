# Systemd Service Installation

This directory contains files to run the Rotary Phone VoIP Controller as a systemd service on a Raspberry Pi.

## Files

- `rotary-phone.service` - Systemd service unit file
- `install.sh` - Installation script
- `uninstall.sh` - Uninstallation script

## Manual Installation

If you prefer to install manually:

```bash
# 1. Copy project to /opt/rotary-phone
sudo mkdir -p /opt/rotary-phone
sudo cp -r ../src /opt/rotary-phone/
sudo cp ../pyproject.toml /opt/rotary-phone/
sudo cp ../config.yaml /opt/rotary-phone/  # Your config file

# 2. Set up Python environment
cd /opt/rotary-phone
sudo uv venv
sudo uv sync

# 3. Install and enable service
sudo cp rotary-phone.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable rotary-phone
sudo systemctl start rotary-phone
```

## Service Commands

```bash
# Start the service
sudo systemctl start rotary-phone

# Stop the service
sudo systemctl stop rotary-phone

# Restart the service
sudo systemctl restart rotary-phone

# Check status
sudo systemctl status rotary-phone

# View logs (live)
sudo journalctl -u rotary-phone -f

# View recent logs
sudo journalctl -u rotary-phone -n 100

# Disable auto-start on boot
sudo systemctl disable rotary-phone
```

## Configuration

The service expects a `config.yaml` file at `/opt/rotary-phone/config.yaml`.

Example configuration:

```yaml
sip:
  server: "seattle.voip.ms"
  port: 5060
  username: "your_username"
  password: "your_password"

speed_dial:
  "11": "+12065551234"
  "12": "+12065555678"

allowlist:
  - "+12065551234"
  - "+12065555678"
```

## Troubleshooting

### Service won't start

1. Check logs: `sudo journalctl -u rotary-phone -n 50`
2. Verify config.yaml exists and is valid YAML
3. Test manually: `/opt/rotary-phone/.venv/bin/rotary-phone`

### GPIO permission errors

The service runs as root with access to the `gpio`, `dialout`, and `audio` groups. If you still have permission issues:

```bash
# Check GPIO permissions
ls -la /dev/gpiomem
ls -la /dev/mem

# Ensure the gpio group exists and has access
sudo groupadd -f gpio
sudo chown root:gpio /dev/gpiomem
sudo chmod g+rw /dev/gpiomem
```

### Audio not working

```bash
# List audio devices
aplay -l
arecord -l

# Test audio output
aplay /usr/share/sounds/alsa/Front_Center.wav

# Check ALSA config
cat /etc/asound.conf
cat ~/.asoundrc
```

### Network issues

The service waits for `network-online.target`. If SIP registration fails:

1. Check network: `ping your-sip-server.com`
2. Verify SIP credentials in config.yaml
3. Check firewall: `sudo ufw status`

## Security Notes

The service file includes security hardening:

- `NoNewPrivileges=true` - Prevents privilege escalation
- `ProtectSystem=strict` - Read-only filesystem except /opt/rotary-phone
- `ProtectHome=true` - No access to home directories
- `PrivateTmp=true` - Isolated /tmp directory

To modify these settings, edit `/etc/systemd/system/rotary-phone.service` and run:

```bash
sudo systemctl daemon-reload
sudo systemctl restart rotary-phone
```
