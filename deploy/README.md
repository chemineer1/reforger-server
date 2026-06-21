# AWS EC2 Deployment

This setup runs the Reforger server with Docker Compose and uses a host-side
systemd service to stop the EC2 instance after 30 minutes with zero players.

## Fast Boot Model

The expensive work should happen once:

1. Build the Docker image during initial setup or planned maintenance.
2. Download the Reforger dedicated server into the named Docker volume.
3. Create the container once with `docker compose up -d`.
4. Let the entrypoint skip SteamCMD when the server executable already exists.

With that flow, a Discord `/reforger start` only starts the EC2 instance,
Docker restarts the existing container, and the container launches the persisted
server files.

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

Clone or copy this repository into the path expected by the deployment scripts:

```sh
sudo mkdir -p /opt/reforger-server
sudo chown "$USER:$USER" /opt/reforger-server
git clone <your-repo-url> /opt/reforger-server
cd /opt/reforger-server
```

Create local config files:

```sh
cp config/config.example.json config/config.json
cp config/FreedomFighters_ServerConfig.example.json config/FreedomFighters_ServerConfig.json
cp config/ec2-idle.env.example config/ec2-idle.env
```

Edit `config/config.json` and change at least:

```text
game.passwordAdmin
rcon.password
publicAddress
```

Set the same RCON password in `config/ec2-idle.env`:

```text
RCON_PASSWORD=your-rcon-password
```

Edit `config/FreedomFighters_ServerConfig.json` with your Discord webhook URL.
Compose mounts that file as a read-only secret and copies it into
`/home/steam/profile/FreedomFighters_ServerConfig.json`, so restart the server
after changing it.

Build the image once and do the first server download:

```sh
docker compose build
docker compose up -d
docker compose logs -f server
```

When the server has finished downloading files and reached normal startup,
install and start the idle shutdown service:

```sh
deploy/install-systemd.sh
docker compose up -d
sudo systemctl start reforger-idle-shutdown.service
```

Leave the Compose container created. The `restart: unless-stopped` policy in
`compose.yaml` lets Docker restart it automatically when the EC2 host boots.

## Host Layout

The included deployment scripts expect the repository at:

```text
/opt/reforger-server
```

The AWS deployment files are grouped by responsibility:

```text
deploy/
|-- install-systemd.sh       # Copies and enables the idle shutdown service
|-- systemd/                 # systemd unit file installed into /etc/systemd/system
|-- idle-shutdown/           # Python watcher that shuts down an idle EC2 host
`-- discord-lambda/          # Optional Discord slash-command Lambda
```

## Install Service

From `/opt/reforger-server`:

```sh
deploy/install-systemd.sh
docker compose up -d
sudo systemctl start reforger-idle-shutdown.service
```

Check status:

```sh
sudo systemctl status reforger-idle-shutdown.service
docker compose ps
```

Follow logs:

```sh
docker compose logs -f server
journalctl -u reforger-idle-shutdown.service -f
```

## Idle Shutdown

The watcher checks the Reforger player count once per minute. By default it
tries `127.0.0.1:19999` using Reforger RCON and runs `#players`; if that query
fails, it falls back to the Steam A2S endpoint on `127.0.0.1:17777`. If a
configured source reports zero players continuously for 30 minutes, it shuts
down the OS.

The defaults are set in `deploy/systemd/reforger-idle-shutdown.service`:

```text
PLAYER_COUNT_SOURCE=rcon,a2s
RCON_HOST=127.0.0.1
RCON_PORT=19999
A2S_HOST=127.0.0.1
A2S_PORT=17777
IDLE_SECONDS=1800
CHECK_INTERVAL_SECONDS=60
STARTUP_GRACE_SECONDS=600
IDLE_ON_QUERY_FAILURE=0
```

`PLAYER_COUNT_SOURCE` can be `rcon`, `a2s`, or an ordered fallback list such as
`rcon,a2s`. You do not need both RCON and A2S, but keeping A2S as a fallback
prevents a bad RCON password or transient RCON failure from being the only
signal.

`IDLE_ON_QUERY_FAILURE=0` means failed player-count checks do not count as idle.
Set it to `1` only if you want a broken or unreachable local server to stop the
instance after the startup grace period plus idle threshold.

## Updating The Server

Normal starts are optimized for speed and skip SteamCMD when the dedicated
server executable already exists. To update the server during planned
maintenance:

```sh
sudo systemctl stop reforger-idle-shutdown.service
docker compose stop
docker compose run --rm --entrypoint /opt/steamcmd/steamcmd.sh server \
  +force_install_dir /home/steam/reforger \
  +login anonymous \
  +app_update 1874900 \
  +quit
docker compose up -d
sudo systemctl start reforger-idle-shutdown.service
```

If you suspect corrupted files, add `validate` before `+quit`.

## Discord Control

Slash-command control for starting, stopping, and checking the EC2 instance is
in:

```text
deploy/discord-lambda
```

See `deploy/discord-lambda/README.md`.
