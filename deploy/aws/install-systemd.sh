#!/usr/bin/env bash
set -Eeuo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
target_dir="/opt/reforger-server"

if [[ "${repo_dir}" != "${target_dir}" ]]; then
  echo "This repo should live at ${target_dir} for the provided systemd units." >&2
  echo "Current path: ${repo_dir}" >&2
  exit 1
fi

sudo install -m 0644 deploy/aws/systemd/reforger-server.service /etc/systemd/system/reforger-server.service
sudo install -m 0644 deploy/aws/systemd/reforger-idle-shutdown.service /etc/systemd/system/reforger-idle-shutdown.service
sudo install -m 0755 deploy/aws/idle-shutdown/reforger_idle_shutdown.py /opt/reforger-server/deploy/aws/idle-shutdown/reforger_idle_shutdown.py

sudo systemctl daemon-reload
sudo systemctl enable reforger-server.service
sudo systemctl enable reforger-idle-shutdown.service

echo "Installed systemd units."
echo "Start with: sudo systemctl start reforger-server.service reforger-idle-shutdown.service"
