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
sudo systemctl disable --now reforger-idle-shutdown.service 2>/dev/null || true
sudo systemctl disable --now reforger-host-agent.service 2>/dev/null || true
sudo rm -f /etc/systemd/system/reforger-server.service
sudo rm -f /etc/systemd/system/reforger-idle-shutdown.service
sudo install -m 0644 "${repo_dir}/deploy/systemd/reforger-host-agent.service" /etc/systemd/system/reforger-host-agent.service
sudo chmod 0755 "${repo_dir}/deploy/host-agent/reforger_host_agent.py"

sudo systemctl daemon-reload
sudo systemctl enable reforger-host-agent.service

echo "Installed systemd unit."
echo "Start the container with: docker compose up -d"
echo "Start host automation with: sudo systemctl start reforger-host-agent.service"
