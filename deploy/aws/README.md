# AWS EC2 Deployment

This setup runs the Reforger server with Docker Compose and uses a host-side
systemd service to stop the EC2 instance after 30 minutes with zero players.

## Fast Boot Model

The expensive work should happen once:

1. Build the Docker image during initial setup or planned maintenance.
2. Download the Reforger dedicated server into the named Docker volume.
3. Let normal EC2 starts run `docker compose up -d` without rebuilding.
4. Let the entrypoint skip SteamCMD when the server executable already exists.

With that flow, a Discord `/reforger start` only starts the EC2 instance,
systemd starts the existing Compose service, and the container launches the
persisted server files.

## EC2 Settings

Use an EBS-backed instance and set **Instance initiated shutdown behavior** to
`Stop`. The idle watcher calls:

```sh
/sbin/shutdown -h now
```

With shutdown behavior set to `Stop`, EC2 stops billing for instance runtime
after the OS shuts down. EBS volume costs still apply.

Open the required UDP ports in the instance security group:

```text
2001/udp   game traffic
17777/udp  Steam A2S query
19999/udp  RCON, restrict this to your admin IP
```

Keep SSH restricted to your IP.

Start with at least 40 GiB of gp3 EBS storage so the base image, server files,
Workshop mods, logs, and Docker layers have room to grow. CPU needs depend on
player count and mission load; use a current general-purpose instance as a
starting point and resize after watching CPU and memory during a real session.

## First-Time Setup

These steps assume Ubuntu 24.04 on EC2.

Install Docker Engine and the Compose plugin using Docker's official Ubuntu
repository instructions, then add your SSH user to the `docker` group:

```sh
sudo usermod -aG docker "$USER"
newgrp docker
docker compose version
```

Clone or copy this repository into the path expected by the systemd units:

```sh
sudo mkdir -p /opt/reforger-server
sudo chown "$USER:$USER" /opt/reforger-server
git clone <your-repo-url> /opt/reforger-server
cd /opt/reforger-server
```

Create local config files:

```sh
cp config/server.example.json config/server.json
cp config/FreedomFighters_ServerConfig.example.json config/FreedomFighters_ServerConfig.json
cp config/ec2-idle.env.example config/ec2-idle.env
```

Edit `config/server.json` and change at least:

```text
game.passwordAdmin
rcon.password
publicAddress
```

Set the same RCON password in `config/ec2-idle.env`:

```text
RCON_PASSWORD=your-rcon-password
```

Build the image once and do the first server download before enabling systemd:

```sh
docker compose build
docker compose up -d
docker compose logs -f reforger
```

When the server has finished downloading files and reached normal startup, stop
it once so systemd owns the lifecycle from here on:

```sh
docker compose down
deploy/aws/install-systemd.sh
sudo systemctl start reforger-server.service reforger-idle-shutdown.service
```

## Host Layout

The included systemd units expect the repository at:

```text
/opt/reforger-server
```

The AWS deployment files are grouped by responsibility:

```text
deploy/aws/
|-- install-systemd.sh       # Copies and enables host services
|-- systemd/                 # systemd unit files installed into /etc/systemd/system
|-- idle-shutdown/           # Python watcher that shuts down an idle EC2 host
`-- discord-lambda/          # Optional Discord slash-command Lambda
```

## Install Services

From `/opt/reforger-server`:

```sh
deploy/aws/install-systemd.sh
sudo systemctl start reforger-server.service reforger-idle-shutdown.service
```

Check status:

```sh
sudo systemctl status reforger-server.service
sudo systemctl status reforger-idle-shutdown.service
docker compose ps
```

Follow logs:

```sh
docker compose logs -f reforger
journalctl -u reforger-idle-shutdown.service -f
```

## Idle Shutdown

The watcher queries `127.0.0.1:19999` using Reforger RCON and runs `#players`.
If the server reports zero players continuously for 30 minutes, it shuts down
the OS.

The defaults are set in `deploy/aws/systemd/reforger-idle-shutdown.service`:

```text
PLAYER_COUNT_SOURCE=rcon
RCON_HOST=127.0.0.1
RCON_PORT=19999
IDLE_SECONDS=1800
CHECK_INTERVAL_SECONDS=60
STARTUP_GRACE_SECONDS=600
IDLE_ON_QUERY_FAILURE=1
```

`IDLE_ON_QUERY_FAILURE=1` means a broken or unreachable local server also stops
the instance after the startup grace period plus idle threshold. Set it to `0`
if you only want confirmed `0/N` A2S responses to count as idle.

## Updating The Server

Normal starts are optimized for speed and skip SteamCMD when the dedicated
server executable already exists. To update the server during planned
maintenance:

```sh
sudo systemctl stop reforger-server.service reforger-idle-shutdown.service
docker compose run --rm --entrypoint /opt/steamcmd/steamcmd.sh reforger \
  +force_install_dir /home/steam/reforger \
  +login anonymous \
  +app_update 1874900 \
  +quit
sudo systemctl start reforger-server.service reforger-idle-shutdown.service
```

If you suspect corrupted files, add `validate` before `+quit`.

## Discord Control

Slash-command control for starting, stopping, and checking the EC2 instance is
in:

```text
deploy/aws/discord-lambda
```

See `deploy/aws/discord-lambda/README.md`.
