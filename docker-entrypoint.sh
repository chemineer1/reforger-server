#!/usr/bin/env bash
set -Eeuo pipefail

server_executable="${SERVER_EXECUTABLE:-${SERVER_DIR}/ArmaReforgerServer}"
steam_update_on_start="${STEAM_UPDATE_ON_START:-missing}"
steam_validate="${STEAM_VALIDATE:-0}"
should_update=0

# Normal EC2 starts should be fast: if the named Docker volume already contains
# the server executable, skip SteamCMD and launch immediately. Set
# STEAM_UPDATE_ON_START=always when intentionally updating the dedicated server.
case "${steam_update_on_start,,}" in
  1 | true | yes | always)
    should_update=1
    ;;
  0 | false | no | never)
    should_update=0
    ;;
  missing | if-missing)
    if [[ ! -x "${server_executable}" ]]; then
      should_update=1
    fi
    ;;
  *)
    echo "Invalid STEAM_UPDATE_ON_START value: ${steam_update_on_start}" >&2
    echo "Use one of: missing, always, never." >&2
    exit 64
    ;;
esac

# Validation is useful after a corrupted install, but it slows normal starts.
if [[ "${steam_validate,,}" == "1" || "${steam_validate,,}" == "true" ]]; then
  should_update=1
fi

if [[ "${should_update}" == "1" ]]; then
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

  if [[ "${steam_validate,,}" == "1" || "${steam_validate,,}" == "true" ]]; then
    steamcmd_args+=(validate)
  fi

  steamcmd_args+=(+quit)

  "${STEAMCMD_DIR}/steamcmd.sh" "${steamcmd_args[@]}"
else
  echo "Skipping SteamCMD update; ${server_executable} already exists."
fi

# Some Steamworks-enabled dedicated servers look for steamclient.so under the
# user's .steam SDK paths rather than directly under the SteamCMD install.
mkdir -p "${HOME}/.steam/sdk32" "${HOME}/.steam/sdk64" "${PROFILE_DIR}"

if [[ -f "${STEAMCMD_DIR}/linux32/steamclient.so" ]]; then
  ln -sf "${STEAMCMD_DIR}/linux32/steamclient.so" "${HOME}/.steam/sdk32/steamclient.so"
fi

if [[ -f "${STEAMCMD_DIR}/linux64/steamclient.so" ]]; then
  ln -sf "${STEAMCMD_DIR}/linux64/steamclient.so" "${HOME}/.steam/sdk64/steamclient.so"
fi

# Freedom Fighters reads this file from the runtime profile directory created
# under the server's -profile root. Copy the Compose secret there on each start
# so the profile volume cannot hold a stale webhook config.
if [[ -n "${FREEDOM_FIGHTERS_CONFIG_FILE:-}" ]]; then
  freedom_fighters_config_source="${FREEDOM_FIGHTERS_CONFIG_SOURCE:-${FREEDOM_FIGHTERS_CONFIG_FILE}}"
  if [[ ! -f "${freedom_fighters_config_source}" ]]; then
    echo "Freedom Fighters config is missing: ${freedom_fighters_config_source}" >&2
    echo "Mount config/FreedomFighters_ServerConfig.json as a secret or set FREEDOM_FIGHTERS_CONFIG_FILE empty." >&2
    exit 78
  fi
  mkdir -p "${FREEDOM_FIGHTERS_CONFIG_FILE%/*}"
  if [[ "${freedom_fighters_config_source}" != "${FREEDOM_FIGHTERS_CONFIG_FILE}" ]]; then
    install -m 0600 "${freedom_fighters_config_source}" "${FREEDOM_FIGHTERS_CONFIG_FILE}"
  fi
fi

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
# Compose workflow expects config/server.json to be mounted read-only.
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
