# syntax=docker/dockerfile:1.7

FROM ubuntu:24.04

ARG USER_ID=10001
ARG GROUP_ID=10001
ARG STEAMCMD_URL="https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz"
ARG DEBIAN_FRONTEND=noninteractive

LABEL org.opencontainers.image.title="Arma Reforger dedicated server" \
      org.opencontainers.image.description="Dedicated Arma Reforger server installed and launched with SteamCMD." \
      org.opencontainers.image.source="https://steamdb.info/app/1874900/"

ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    STEAMCMD_DIR=/opt/steamcmd \
    SERVER_DIR=/home/steam/reforger \
    PROFILE_DIR=/home/steam \
    CONFIG_FILE=/run/configs/reforger-server.json \
    FREEDOM_FIGHTERS_CONFIG_SOURCE=/run/secrets/freedom_fighters_server_config \
    FREEDOM_FIGHTERS_CONFIG_FILE=/home/steam/profile/FreedomFighters_ServerConfig.json \
    STEAM_APP_ID=1874900 \
    STEAM_BRANCH=public \
    STEAM_VALIDATE=0 \
    SERVER_MAX_FPS=60

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# SteamCMD is a 32-bit Linux application, so the image enables i386 packages
# and installs the small compatibility runtime it needs.
RUN set -eux; \
    dpkg --add-architecture i386; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        gzip \
        lib32gcc-s1 \
        lib32stdc++6 \
        libcurl4 \
        libssl3t64 \
        tar; \
    # Run the server as an unprivileged user while keeping UID/GID configurable
    # for hosts that care about volume ownership.
    groupadd --gid "${GROUP_ID}" steam; \
    useradd --uid "${USER_ID}" --gid steam --create-home --shell /usr/sbin/nologin steam; \
    install -d -o steam -g steam -m 0755 "${STEAMCMD_DIR}" "${SERVER_DIR}" "${PROFILE_DIR}" "${PROFILE_DIR}/profile"; \
    # Install SteamCMD itself at build time; game server files are downloaded
    # at container startup into the Compose-managed server volume.
    curl --fail --location --show-error --silent --retry 5 --retry-delay 2 "${STEAMCMD_URL}" \
        | tar --extract --gzip --directory "${STEAMCMD_DIR}"; \
    chown -R steam:steam "${STEAMCMD_DIR}" /home/steam; \
    rm -rf /var/lib/apt/lists/*

COPY --chmod=0755 docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

USER steam
WORKDIR /home/steam

EXPOSE 2001/udp 17777/udp 19999/udp

# Compose supplies `init: true`; this script can therefore run directly as PID 1
# under Docker's built-in init wrapper.
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
