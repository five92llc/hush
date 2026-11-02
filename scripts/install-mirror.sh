#!/usr/bin/env bash
# Installs what Hush needs to receive AirPlay screen mirroring from iPhones, iPads and Macs (Ubuntu or Debian).
# Run once on the Hush server:  sudo ./scripts/install-mirror.sh   then switch it on in Settings -> Mirroring.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y uxplay xvfb pulseaudio pulseaudio-utils x11-utils avahi-daemon \
  gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-libav gstreamer1.0-pulseaudio gstreamer1.0-x gstreamer1.0-tools
systemctl enable --now avahi-daemon || true
echo "Done. In Hush: Settings -> Mirroring -> AirPlay (iPhone, iPad, Mac) -> on."
