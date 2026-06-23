#!/usr/bin/env python3
"""Run host-side Reforger automation for an EC2 server.

The agent queries Reforger for player count, sends optional ready notifications,
and tracks confirmed idle time. It is intentionally host-side: the game
container keeps running the game, while systemd on the EC2 instance handles
automation around it.
"""

from __future__ import annotations

import json
import logging
import os
import shlex
import socket
import struct
import subprocess
import time
import urllib.error
import urllib.request


A2S_QUERY = b"\xff\xff\xff\xffTSource Engine Query\x00"
S2A_INFO = 0x49
S2A_CHALLENGE = 0x41
DEFAULT_READY_MESSAGE = "Arma Reforger server is online and ready to join."


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def send_discord_webhook(webhook_url: str, message: str, timeout: float) -> None:
    """Send a simple Discord webhook message."""
    body = json.dumps(
        {
            "content": message,
            "allowed_mentions": {"parse": []},
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        webhook_url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "reforger-host-agent/1.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = response.getcode()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Discord webhook failed with HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Discord webhook failed: {exc.reason}") from exc

    if status < 200 or status >= 300:
        raise RuntimeError(f"Discord webhook failed with HTTP {status}")


def notification_already_sent(state_file: str) -> bool:
    return bool(state_file) and os.path.exists(state_file)


def mark_notification_sent(state_file: str) -> None:
    if not state_file:
        return
    state_dir = os.path.dirname(state_file)
    if state_dir:
        os.makedirs(state_dir, exist_ok=True)
    with open(state_file, "w", encoding="utf-8") as file:
        file.write(f"{int(time.time())}\n")


def read_c_string(payload: bytes, offset: int) -> tuple[str, int]:
    end = payload.index(0, offset)
    return payload[offset:end].decode("utf-8", errors="replace"), end + 1


def query_player_count(host: str, port: int, timeout: float) -> tuple[int, int]:
    """Return (players, max_players) from the A2S_INFO response."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        sock.sendto(A2S_QUERY, (host, port))
        response, _ = sock.recvfrom(4096)

        if not response.startswith(b"\xff\xff\xff\xff"):
            raise ValueError("unsupported split or malformed A2S response")

        payload = response[4:]
        if payload and payload[0] == S2A_CHALLENGE:
            if len(payload) < 5:
                raise ValueError("malformed A2S challenge response")
            sock.sendto(A2S_QUERY + payload[1:5], (host, port))
            response, _ = sock.recvfrom(4096)
            if not response.startswith(b"\xff\xff\xff\xff"):
                raise ValueError("unsupported split or malformed A2S response")
            payload = response[4:]

        if not payload or payload[0] != S2A_INFO:
            raise ValueError("unexpected A2S response type")

        offset = 2
        _, offset = read_c_string(payload, offset)  # server name
        _, offset = read_c_string(payload, offset)  # map
        _, offset = read_c_string(payload, offset)  # folder
        _, offset = read_c_string(payload, offset)  # game
        offset += struct.calcsize("<H")  # Steam app ID

        players = payload[offset]
        max_players = payload[offset + 1]
        return players, max_players


def main() -> int:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(message)s",
    )

    a2s_host = os.getenv("A2S_HOST", "127.0.0.1")
    a2s_port = int(os.getenv("A2S_PORT", "17777"))
    timeout = float(os.getenv("QUERY_TIMEOUT_SECONDS", "5"))
    check_interval = int(os.getenv("CHECK_INTERVAL_SECONDS", "60"))
    idle_seconds = int(os.getenv("IDLE_SECONDS", "1800"))
    startup_grace_seconds = int(os.getenv("STARTUP_GRACE_SECONDS", "600"))
    idle_on_query_failure = env_bool("IDLE_ON_QUERY_FAILURE", False)
    dry_run = env_bool("DRY_RUN", False)
    shutdown_command = os.getenv("SHUTDOWN_COMMAND", "/sbin/shutdown -h now")
    discord_ready_webhook_url = os.getenv("DISCORD_READY_WEBHOOK_URL", "")
    discord_ready_message = os.getenv("DISCORD_READY_MESSAGE", DEFAULT_READY_MESSAGE)
    ready_state_file = os.getenv(
        "DISCORD_READY_STATE_FILE",
        "/run/reforger-ready-notified",
    )

    idle_started_at: float | None = None
    started_at = time.monotonic()
    ready_notification_sent = notification_already_sent(ready_state_file)

    logging.info(
        "watching player count via A2S at %s:%s; idle threshold=%ss; interval=%ss",
        a2s_host,
        a2s_port,
        idle_seconds,
        check_interval,
    )

    while True:
        now = time.monotonic()
        in_startup_grace = now - started_at < startup_grace_seconds

        try:
            players, max_players = query_player_count(a2s_host, a2s_port, timeout)
            logging.info("player count via A2S: %s/%s", players, max_players)
            if discord_ready_webhook_url and not ready_notification_sent:
                try:
                    send_discord_webhook(
                        discord_ready_webhook_url,
                        discord_ready_message,
                        timeout,
                    )
                    logging.info("sent Discord ready notification")
                    try:
                        mark_notification_sent(ready_state_file)
                    except OSError as exc:
                        logging.warning(
                            "could not write ready notification state: %s",
                            exc,
                        )
                    ready_notification_sent = True
                except Exception as exc:  # noqa: BLE001 - retry on the next loop
                    logging.warning("Discord ready notification failed: %s", exc)
            is_idle = players == 0
        except Exception as exc:  # noqa: BLE001 - daemon should keep running
            logging.warning("player count query failed: %s", exc)
            is_idle = idle_on_query_failure and not in_startup_grace

        if is_idle:
            if idle_started_at is None:
                idle_started_at = now
                logging.info("idle timer started")

            idle_for = int(now - idle_started_at)
            logging.info("idle for %ss/%ss", idle_for, idle_seconds)
            if idle_for >= idle_seconds:
                logging.warning("idle threshold reached; stopping EC2 instance")
                if dry_run:
                    logging.warning("dry run enabled; not running shutdown command")
                    idle_started_at = now
                else:
                    subprocess.run(shlex.split(shutdown_command), check=False)
                    return 0
        else:
            if idle_started_at is not None:
                logging.info("players detected; idle timer reset")
            idle_started_at = None

        time.sleep(check_interval)


if __name__ == "__main__":
    raise SystemExit(main())
