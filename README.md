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

Build and start the server:

```sh
docker compose up -d --build
```

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
