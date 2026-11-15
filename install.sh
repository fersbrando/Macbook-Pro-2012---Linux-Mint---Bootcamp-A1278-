#!/usr/bin/env bash
# Boot Camp for Linux — installer
#
#   One line:   curl -fsSL https://raw.githubusercontent.com/fersbrando/Macbook-Pro-2012---Linux-Mint---Bootcamp-A1278-/main/install.sh | bash
#   From clone: ./install.sh [--no-fan]
#
#   --no-fan   do not install/replace the fancontrold service
set -euo pipefail

REPO="fersbrando/Macbook-Pro-2012---Linux-Mint---Bootcamp-A1278-"
BRANCH="main"
PREFIX="/opt/bootcamp"
FANLIB="/usr/local/lib/fancontrol"
INSTALL_FAN=1
for arg in "$@"; do
  case "$arg" in
    --no-fan) INSTALL_FAN=0 ;;
    -h|--help) sed -n '2,8p' "$0"; exit 0 ;;
  esac
done

blue() { printf '\033[1;34m→ %s\033[0m\n' "$*"; }
ok()   { printf '\033[1;32m✓ %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m! %s\033[0m\n' "$*"; }

if [ "$(id -u)" -eq 0 ]; then
  echo "Run this as your normal user (it will ask for sudo when needed)." >&2
  exit 1
fi

# ---------------------------------------------------------------- source files
SRC="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || true)"
if [ -z "$SRC" ] || [ ! -f "$SRC/bootcamp.py" ]; then
  blue "Downloading Boot Camp from GitHub..."
  TMP="$(mktemp -d)"
  trap 'rm -rf "$TMP"' EXIT
  curl -fsSL "https://github.com/$REPO/archive/refs/heads/$BRANCH.tar.gz" | tar -xz -C "$TMP" --strip-components=1
  SRC="$TMP"
fi

# ---------------------------------------------------------------- dependencies
blue "Checking dependencies..."
PKGS=(python3 python3-gi python3-gi-cairo gir1.2-gtk-3.0 xinput pulseaudio-utils pkexec upower mesa-utils pciutils usbutils)
MISSING=()
for p in "${PKGS[@]}"; do
  dpkg -s "$p" >/dev/null 2>&1 || MISSING+=("$p")
done
if [ ${#MISSING[@]} -gt 0 ]; then
  blue "Installing: ${MISSING[*]}"
  sudo apt-get update -qq
  # pkexec is called policykit-1 on older releases
  sudo apt-get install -y "${MISSING[@]}" || sudo apt-get install -y "${MISSING[@]/pkexec/policykit-1}"
fi

# ---------------------------------------------------------------- application
blue "Installing application to $PREFIX..."
sudo rm -rf "$PREFIX"
sudo install -d -m 755 "$PREFIX" "$PREFIX/bc" "$PREFIX/fancontrol"
sudo install -m 755 "$SRC/bootcamp.py" "$SRC/bc_helper.py" "$PREFIX/"
sudo install -m 644 "$SRC/icono.png" "$PREFIX/"
sudo install -m 644 "$SRC"/bc/*.py "$PREFIX/bc/"
sudo install -m 644 "$SRC"/fancontrol/*.py "$PREFIX/fancontrol/"
sudo ln -sf "$PREFIX/bootcamp.py" /usr/local/bin/bootcamp

blue "Adding menu entry and icon..."
for size in 48 64 128 256; do
  dir="/usr/share/icons/hicolor/${size}x${size}/apps"
  sudo install -d "$dir"
  python3 - "$SRC/icono.png" "$size" <<'PY' | sudo tee "$dir/bootcamp.png" >/dev/null
import sys, gi
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf
pb = GdkPixbuf.Pixbuf.new_from_file_at_size(sys.argv[1], int(sys.argv[2]), int(sys.argv[2]))
ok, data = pb.save_to_bufferv("png", [], [])
sys.stdout.buffer.write(data)
PY
done
sudo gtk-update-icon-cache -q -f /usr/share/icons/hicolor 2>/dev/null || true
sudo install -m 644 "$SRC/packaging/bootcamp.desktop" /usr/share/applications/bootcamp.desktop
sudo update-desktop-database -q /usr/share/applications 2>/dev/null || true
sudo install -m 644 "$SRC/packaging/io.github.fersbrando.bootcamp.policy" /usr/share/polkit-1/actions/

# Trackpad autostart created by an older version: point it to the installed command
AUTO="$HOME/.config/autostart/bootcamp.desktop"
if [ -f "$AUTO" ]; then
  sed -i 's|^Exec=.*|Exec=bootcamp --apply|' "$AUTO"
fi

# ---------------------------------------------------------------- fan service
if [ "$INSTALL_FAN" -eq 1 ]; then
  if ! sudo modprobe applesmc 2>/dev/null || [ ! -d /sys/devices/platform/applesmc.768 ]; then
    warn "Apple SMC (applesmc) not found: skipping fan service."
  else
    blue "Installing fan service (fancontrold)..."
    sudo install -d -m 755 "$FANLIB"
    sudo install -m 644 "$SRC/fancontrol/fanlib.py" "$FANLIB/fanlib.py"
    sudo install -m 755 "$SRC/fancontrol/fancontrold.py" "$SRC/fancontrol/fanalert.py" "$FANLIB/"
    # Users in the sudo group can change the fan settings from the GUI without a password
    sudo install -d -m 775 -g sudo /etc/fancontrol
    if [ ! -s /etc/fancontrol/config.json ]; then
      sudo python3 -c "import sys,json; sys.path.insert(0,'$FANLIB'); import fanlib; json.dump(fanlib.DEFAULT_CONFIG, open('/etc/fancontrol/config.json','w'), indent=2)"
    fi
    sudo chgrp sudo /etc/fancontrol/config.json
    sudo chmod 664 /etc/fancontrol/config.json
    grep -qx applesmc /etc/modules || echo applesmc | sudo tee -a /etc/modules >/dev/null

    sudo tee /etc/systemd/system/fancontrold.service >/dev/null <<UNIT
[Unit]
Description=Control de ventilador MacBook Pro (applesmc)
After=systemd-modules-load.service

[Service]
Type=simple
ExecStartPre=-/sbin/modprobe applesmc
ExecStart=/usr/bin/python3 $FANLIB/fancontrold.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT
    if systemctl is-enabled mbpfan >/dev/null 2>&1; then
      warn "Disabling mbpfan (it would fight with fancontrold)"
      sudo systemctl disable --now mbpfan
    fi
    sudo systemctl daemon-reload
    sudo systemctl enable fancontrold >/dev/null 2>&1
    sudo systemctl restart fancontrold

    # Desktop temperature alerts (same file name as the standalone fancontroler, so no duplicates)
    mkdir -p "$HOME/.config/autostart"
    cat > "$HOME/.config/autostart/fanalert.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=Boot Camp – temperature alerts
Exec=python3 $FANLIB/fanalert.py
Icon=bootcamp
Terminal=false
NoDisplay=true
X-GNOME-Autostart-enabled=true
DESK
    pkill -f "fanalert.py" 2>/dev/null || true
    if [ -n "${DISPLAY:-}" ]; then
      nohup python3 "$FANLIB/fanalert.py" >/dev/null 2>&1 &
    fi
  fi
fi

sudo install -m 755 "$SRC/uninstall.sh" /opt/bootcamp-uninstall.sh

echo
ok "Boot Camp installed."
echo "   Open it from the menu (Boot Camp) or run:  bootcamp"
echo "   Uninstall:  /opt/bootcamp-uninstall.sh   (add --all to also remove the fan service)"
