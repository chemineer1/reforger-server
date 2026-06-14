#!/usr/bin/env bash
set -Eeuo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
target_dir="/opt/reforger-server"

if [[ "${repo_dir}" != "${target_dir}" ]]; then
  echo "This repo should live at ${target_dir} for the provided systemd unit." >&2
  echo "Current path: ${repo_dir}" >&2
  exit 1
fi

sudo systemctl disable --now reforger-server.service 2>/dev/null || true
sudo rm -f /etc/systemd/system/reforger-server.service
sudo install -m 0644 "${repo_dir}/deploy/systemd/reforger-idle-shutdown.service" /etc/systemd/system/reforger-idle-shutdown.service
sudo chmod 0755 "${repo_dir}/deploy/idle-shutdown/reforger_idle_shutdown.py"

sudo systemctl daemon-reload
sudo systemctl enable reforger-idle-shutdown.service

echo "Installed systemd unit."
echo "Start the container with: docker compose up -d"
echo "Start idle shutdown with: sudo systemctl start reforger-idle-shutdown.service"
