# Arma Reforger Dedicated Server

This project is managed with the modern Docker Compose plugin.

## Usage

The local server config lives at:

```text
config/config.json
```

It is ignored by git because it can contain server passwords and admin IDs. Pick a tracked scenario example and copy it into place whenever you want to switch modes.

For regular Game Master:

```sh
cp config/config.SandboxExample.json config/config.json
```

For Freedom Fighters:

```sh
cp config/config.FfExample.json config/config.json
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

## Scenario Profiles

The base Compose service is scenario-agnostic. It mounts only `config/config.json`
as the Reforger server config and does not assume a specific mission or mod.

The Game Master example uses the Everon Game Master scenario:

```text
{59AD59368755F41A}Missions/21_GM_Eden.conf
```

The Freedom Fighters profile uses the Everon Freedom Fighters scenario and
Workshop mod:

```text
{64B2F8D8059EE270}Missions/FreedomFighters/Everon.conf
CAFEBEEFF0CACC1A
```

Freedom Fighters also has an optional mod config:

```text
config/FreedomFighters_ServerConfig.json
```

Create it from the tracked example when you need Discord/webhook settings:

```sh
cp config/FreedomFighters_ServerConfig.example.json config/FreedomFighters_ServerConfig.json
```

Run Compose with the Freedom Fighters override so that file is mounted as a
secret and copied into `/home/steam/profile/FreedomFighters_ServerConfig.json`:

```sh
docker compose -f compose.yaml -f compose.freedom-fighters.yaml up -d --build
```

For other scenarios that need an extra profile file, add a small Compose
override that sets `PROFILE_CONFIG_SOURCE` and `PROFILE_CONFIG_FILE`. The
entrypoint will copy the mounted source into the runtime profile before launch.

Build and start the server:

```sh
docker compose up -d --build
```

The first start downloads the dedicated server into the
`reforger_server-files` Docker volume. Later starts skip SteamCMD by
default so EC2 boots are faster. To intentionally update the dedicated server,
stop the container and run SteamCMD against the persisted volume:

```sh
docker compose stop
docker compose run --rm --entrypoint /opt/steamcmd/steamcmd.sh server \
  +force_install_dir /home/steam/reforger \
  +login anonymous \
  +app_update 1874900 \
  +quit
docker compose up -d
```

On an EC2 host, use the update procedure in `deploy/README.md` so the container
and idle shutdown service are stopped and restarted cleanly around the SteamCMD
update.

The Compose service uses Docker's `unless-stopped` restart policy. If the
server keeps restarting after repeated failures, check the logs before starting
it again.

Follow logs:

```sh
docker compose logs -f server
```

Stop the server:

```sh
docker compose stop
```

The dedicated server files and profile data are stored in named Docker volumes:

```text
reforger_server-files
reforger_profile
```

## AWS EC2

AWS host setup and the 30-minute zero-player shutdown watcher live in:

```text
deploy
```

See `deploy/README.md` before installing on an EC2 instance.

## Project Layout

```text
.
|-- compose.yaml                 # Local and EC2 Docker Compose service
|-- compose.freedom-fighters.yaml # Optional Freedom Fighters profile override
|-- Dockerfile                   # Dedicated server container image
|-- docker-entrypoint.sh         # Container startup and SteamCMD/update logic
|-- config/                      # Tracked example configs; local secrets are ignored
`-- deploy/
    |-- install-systemd.sh       # Installs the idle shutdown service on EC2
    |-- systemd/                 # Host service unit
    |-- idle-shutdown/           # Zero-player EC2 shutdown watcher
    `-- discord-lambda/          # Optional Discord slash-command Lambda
```
