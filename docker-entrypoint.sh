#!/usr/bin/env bash
set -Eeuo pipefail

# Build the SteamCMD command incrementally so branch and validation settings can
# be controlled from Compose environment variables.
steamcmd_args=(
  +force_install_dir "${SERVER_DIR}"
  +login anonymous
)

steamcmd_args+=(+app_update "${STEAM_APP_ID}")

# Keep the default on the public branch, but allow Compose overrides for public
# beta branches.
if [[ -n "${STEAM_BRANCH}" && "${STEAM_BRANCH}" != "public" ]]; then
  steamcmd_args+=(-beta "${STEAM_BRANCH}")
fi

# Validation is useful after a corrupted install, but it slows normal starts.
if [[ "${STEAM_VALIDATE}" == "1" || "${STEAM_VALIDATE}" == "true" ]]; then
  steamcmd_args+=(validate)
fi

steamcmd_args+=(+quit)

"${STEAMCMD_DIR}/steamcmd.sh" "${steamcmd_args[@]}"

# Some Steamworks-enabled dedicated servers look for steamclient.so under the
# user's .steam SDK paths rather than directly under the SteamCMD install.
mkdir -p "${HOME}/.steam/sdk32" "${HOME}/.steam/sdk64" "${PROFILE_DIR}"

if [[ -f "${STEAMCMD_DIR}/linux32/steamclient.so" ]]; then
  ln -sf "${STEAMCMD_DIR}/linux32/steamclient.so" "${HOME}/.steam/sdk32/steamclient.so"
fi

if [[ -f "${STEAMCMD_DIR}/linux64/steamclient.so" ]]; then
  ln -sf "${STEAMCMD_DIR}/linux64/steamclient.so" "${HOME}/.steam/sdk64/steamclient.so"
fi

# Freedom Fighters expects its optional mod-specific config in the server
# profile directory. Keep the source file in ./config so it can be edited with
# the main Reforger config, then copy it into the writable profile volume.
if [[ -n "${FREEDOM_FIGHTERS_CONFIG_FILE:-}" && -f "${FREEDOM_FIGHTERS_CONFIG_FILE}" ]]; then
  cp "${FREEDOM_FIGHTERS_CONFIG_FILE}" "${PROFILE_DIR}/FreedomFighters_ServerConfig.json"
fi

server_executable="${SERVER_EXECUTABLE:-${SERVER_DIR}/ArmaReforgerServer}"

# Fail before launch if SteamCMD did not produce the expected server binary.
if [[ ! -x "${server_executable}" ]]; then
  echo "Server executable is missing or is not executable: ${server_executable}" >&2
  exit 70
fi

# These are container defaults. Extra server arguments can still be appended
# after `docker compose run reforger ...` or by overriding the Compose command.
launch_args=(
  -profile "${PROFILE_DIR}"
  -backendlog
  -nothrow
  -maxFPS "${SERVER_MAX_FPS}"
)

# CONFIG_FILE can be set empty for advanced manual launches, but the normal
# Compose workflow expects ./config/server.json to be mounted read-only.
if [[ -n "${CONFIG_FILE}" ]]; then
  if [[ ! -f "${CONFIG_FILE}" ]]; then
    echo "Server config is missing: ${CONFIG_FILE}" >&2
    echo "Mount a config file at that path or set CONFIG_FILE to another path." >&2
    exit 78
  fi
  launch_args+=(-config "${CONFIG_FILE}")
fi

# The server resolves core addon paths such as ./addons relative to the current
# working directory, so run it from the SteamCMD install target.
cd "${SERVER_DIR}"

# Replace the shell with the server so Docker's init process can forward
# signals cleanly and reap children.
exec "${server_executable}" "${launch_args[@]}" "$@"
