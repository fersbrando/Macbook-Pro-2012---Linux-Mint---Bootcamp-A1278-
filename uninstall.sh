#!/usr/bin/env bash
# Boot Camp for Linux — uninstaller
#   ./uninstall.sh          remove the app (keeps the fan service and system tweaks)
#   ./uninstall.sh --all    also remove fancontrold, keyboard (hid_apple) and lid (logind) tweaks
set -uo pipefail
ALL=0
[ "${1:-}" = "--all" ] && ALL=1

echo "→ Removing Boot Camp..."
sudo rm -rf /opt/bootcamp
sudo rm -f /usr/local/bin/bootcamp /usr/share/applications/bootcamp.desktop \
           /usr/share/polkit-1/actions/io.github.fersbrando.bootcamp.policy
sudo rm -f /usr/share/icons/hicolor/{48x48,64x64,128x128,256x256}/apps/bootcamp.png
sudo gtk-update-icon-cache -q -f /usr/share/icons/hicolor 2>/dev/null || true
sudo update-desktop-database -q /usr/share/applications 2>/dev/null || true
rm -f "$HOME/.config/autostart/bootcamp.desktop"

if [ "$ALL" -eq 1 ]; then
  echo "→ Removing fan service (the SMC takes back control of the fan)..."
  sudo systemctl disable --now fancontrold 2>/dev/null
  sudo rm -f /etc/systemd/system/fancontrold.service
  sudo systemctl daemon-reload
  sudo rm -rf /usr/local/lib/fancontrol /etc/fancontrol
  pkill -f fanalert.py 2>/dev/null
  rm -f "$HOME/.config/autostart/fanalert.desktop"

  echo "→ Removing keyboard and lid tweaks..."
  if [ -f /etc/modprobe.d/bootcamp-hid_apple.conf ]; then
    sudo rm -f /etc/modprobe.d/bootcamp-hid_apple.conf
    sudo update-initramfs -u >/dev/null 2>&1
  fi
  if [ -f /etc/systemd/logind.conf.d/bootcamp.conf ]; then
    sudo rm -f /etc/systemd/logind.conf.d/bootcamp.conf
    sudo systemctl kill -s HUP systemd-logind
  fi
fi
sudo rm -f /opt/bootcamp-uninstall.sh
echo "✓ Boot Camp uninstalled. Trackpad/display/sound settings stay as you left them."
