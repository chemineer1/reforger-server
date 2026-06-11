# Arma Reforger Dedicated Server

This project is managed with the modern Docker Compose plugin.

## Usage

The local server config lives at:

```text
config/server.json
```

It is ignored by git because it can contain server passwords and admin IDs. A starter config is already present; reset it from the tracked example whenever needed:

```sh
cp config/server.example.json config/server.json
```

Before opening the server publicly, change at least:

```text
game.name
game.passwordAdmin
game.admins
publicAddress
```

Keep `bindAddress` and `publicAddress` empty unless you have a specific reason to bind or advertise a specific address. The current dedicated server binary rejects `bindPort: 0`, and it requires `a2s.address` to be an IPv4 address when the `a2s` block is present, so this template keeps the documented/default ports explicit and uses `0.0.0.0` for A2S binding.

RCON is enabled on `19999/udp`, matching the Compose port mapping. Change `rcon.password` before exposing the server.

This repo is set up for Freedom Fighters by default. The Reforger config uses the Freedom Fighters Workshop mod:

```text
CAFEBEEFF0CACC1A
```

and the Everon Freedom Fighters scenario:

```text
{64B2F8D8059EE270}Missions/FreedomFighters/Everon.conf
```

The optional Freedom Fighters mod config lives at:

```text
config/FreedomFighters_ServerConfig.json
```

It is copied into the server profile volume as `FreedomFighters_ServerConfig.json` on startup, which is where the mod expects it.

To enable Freedom Fighters status updates in Discord, create or edit that file
from the tracked example:

```sh
cp config/FreedomFighters_ServerConfig.example.json config/FreedomFighters_ServerConfig.json
```

Then set `discord.webhookUrl` to a Discord webhook URL:

```json
{
  "discord": {
    "webhookUrl": "https://discord.com/api/webhooks/..."
  }
}
```

Get the webhook URL from Discord by opening the target channel's settings, then
**Integrations** -> **Webhooks** -> **New Webhook** or an existing webhook ->
**Copy Webhook URL**. Keep this URL private; anyone with it can post to that
channel.

Build and start the server:

```sh
docker compose up -d --build
```

The first start downloads the dedicated server into the
`reforger-server_reforger-server` Docker volume. Later starts skip SteamCMD by
default so EC2 boots are faster. To intentionally update the dedicated server,
stop the service and run SteamCMD against the persisted volume:

```sh
docker compose stop
docker compose run --rm --entrypoint /opt/steamcmd/steamcmd.sh reforger \
  +force_install_dir /home/steam/reforger \
  +login anonymous \
  +app_update 1874900 \
  +quit
docker compose up -d
```

On an EC2 host installed with the systemd units, use the update procedure in
`deploy/README.md` so the `reforger-server` and idle-shutdown services are
stopped and restarted cleanly around the SteamCMD update.

The service retries failed starts up to five times. If the server stops after repeated failures, check the logs before starting it again.

Follow logs:

```sh
docker compose logs -f reforger
```

Stop the server:

```sh
docker compose stop
```

The dedicated server files and profile data are stored in named Docker volumes:

```text
reforger-server_reforger-server
reforger-server_reforger-profile
```

## AWS EC2

AWS host setup, systemd units, and the 30-minute zero-player shutdown watcher live in:

```text
deploy
```

See `deploy/README.md` before installing on an EC2 instance.

## Project Layout

```text
.
|-- compose.yaml                 # Local and EC2 Docker Compose service
|-- Dockerfile                   # Dedicated server container image
|-- docker-entrypoint.sh         # Container startup and SteamCMD/update logic
|-- config/                      # Tracked example configs; local secrets are ignored
`-- deploy/
    |-- install-systemd.sh       # Installs the host services on EC2
    |-- systemd/                 # Host service units
    |-- idle-shutdown/           # Zero-player EC2 shutdown watcher
    `-- discord-lambda/          # Optional Discord slash-command Lambda
```
