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

Build and start the server:

```sh
docker compose up -d --build
```

The service retries failed starts up to five times. If the server stops after repeated failures, check the logs before starting it again.

Follow logs:

```sh
docker compose logs -f reforger
```

Stop the server:

```sh
docker compose down
```

The dedicated server files and profile data are stored in named Docker volumes:

```text
reforger-server_reforger-server
reforger-server_reforger-profile
```
