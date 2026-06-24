# AWS EC2 Deployment

This setup runs the Reforger server with Docker Compose and uses a host-side
systemd agent for server-ready notifications and zero-player EC2 shutdown.

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
`Stop`. The host agent calls:

```sh
/sbin/shutdown -h now
```

With shutdown behavior set to `Stop`, EC2 stops billing for instance runtime
after the OS shuts down. EBS volume costs still apply.

Open the required UDP ports in the instance security group:

```text
2001/udp   game traffic
17777/udp  Steam A2S query
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
cp config/ec2-agent.env.example config/ec2-agent.env
```

Edit `config/config.json` and change at least:

```text
game.passwordAdmin
publicAddress
```

To announce when the game server is actually reachable, add a Discord webhook
URL to `config/ec2-agent.env`:

```text
DISCORD_READY_WEBHOOK_URL=https://discord.com/api/webhooks/...
DISCORD_READY_MESSAGE=Arma Reforger server is online and ready to join.
```

The host agent sends this message once per EC2 boot after the first successful
A2S player-count query. That is later than Docker startup and lines up with the
server responding on its query port.

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
install and start the host agent:

```sh
deploy/install-systemd.sh
docker compose up -d
sudo systemctl start reforger-host-agent.service
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
|-- install-systemd.sh       # Copies and enables the host agent service
|-- systemd/                 # systemd unit file installed into /etc/systemd/system
|-- host-agent/              # Host-side notifications and idle shutdown
`-- discord-lambda/          # Optional Discord slash-command Lambda
```

## Install Service

From `/opt/reforger-server`:

```sh
deploy/install-systemd.sh
docker compose up -d
sudo systemctl start reforger-host-agent.service
```

Check status:

```sh
sudo systemctl status reforger-host-agent.service
docker compose ps
```

Follow logs:

```sh
docker compose logs -f server
journalctl -u reforger-host-agent.service -f
```

## Idle Shutdown

The host agent checks the Reforger player count once per minute using the Steam
A2S endpoint on `127.0.0.1:17777`. If A2S reports zero players continuously for
30 minutes, it shuts down the OS.

The defaults are set in `deploy/systemd/reforger-host-agent.service`:

```text
A2S_HOST=127.0.0.1
A2S_PORT=17777
IDLE_SECONDS=1800
CHECK_INTERVAL_SECONDS=60
STARTUP_GRACE_SECONDS=600
IDLE_ON_QUERY_FAILURE=0
```

`IDLE_ON_QUERY_FAILURE=0` means failed player-count checks do not count as idle.
Set it to `1` only if you want a broken or unreachable local server to stop the
instance after the startup grace period plus idle threshold.

If `DISCORD_READY_WEBHOOK_URL` is set, the host agent posts
`DISCORD_READY_MESSAGE` once when the first A2S player-count query succeeds. The
default state file is `/run/reforger-ready-notified`, so repeated systemd
restarts during the same EC2 boot do not resend the ready message.

## Updating The Server

Normal starts are optimized for speed and skip SteamCMD when the dedicated
server executable already exists. To update the server during planned
maintenance:

```sh
sudo systemctl stop reforger-host-agent.service
docker compose stop
docker compose run --rm --entrypoint /opt/steamcmd/steamcmd.sh server \
  +force_install_dir /home/steam/reforger \
  +login anonymous \
  +app_update 1874900 \
  +quit
docker compose up -d
sudo systemctl start reforger-host-agent.service
```

If you suspect corrupted files, add `validate` before `+quit`.

## Discord Control

Slash-command control for starting, stopping, and checking the EC2 instance is
in:

```text
deploy/discord-lambda
```

See `deploy/discord-lambda/README.md`.
