#!/usr/bin/env python3
"""Stop an EC2 host after the Reforger server has been idle long enough.

The script queries Reforger for player count and tracks confirmed idle time. It
is intentionally host-side: the game container keeps running the game, while
systemd on the EC2 instance decides whether the instance should shut down.
"""

from __future__ import annotations

import logging
import os
import re
import shlex
import socket
import struct
import subprocess
import time
import zlib


A2S_QUERY = b"\xff\xff\xff\xffTSource Engine Query\x00"
S2A_INFO = 0x49
S2A_CHALLENGE = 0x41


class RconError(RuntimeError):
    """Raised when a BattlEye RCON request cannot produce usable output."""


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


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


def battleye_packet(payload: bytes) -> bytes:
    body = b"\xff" + payload
    checksum = (zlib.crc32(body) & 0xFFFFFFFF).to_bytes(4, "little")
    return b"BE" + checksum + body


def battleye_payload(packet: bytes) -> bytes:
    if len(packet) < 8 or not packet.startswith(b"BE"):
        raise RconError("malformed RCON packet")

    payload = packet[6:]
    expected = int.from_bytes(packet[2:6], "little")
    actual = zlib.crc32(payload) & 0xFFFFFFFF
    if expected != actual:
        raise RconError("RCON checksum mismatch")
    if payload[0] != 0xFF:
        raise RconError("malformed RCON payload")
    return payload[1:]


def parse_rcon_player_count(output: str) -> int:
    normalized = output.strip()
    if not normalized:
        raise RconError("empty #players response")

    lower = normalized.lower()
    if "no players" in lower:
        return 0

    total_match = re.search(r"\b(\d+)\s+players?\s+(?:in\s+)?total\b", lower)
    if total_match:
        return int(total_match.group(1))

    count_match = re.search(r"\bplayers?\s*[:=]\s*(\d+)\b", lower)
    if count_match:
        return int(count_match.group(1))

    player_rows = [
        line
        for line in normalized.splitlines()
        if re.match(r"^\s*(?:#?\d+\b|\[\d+\])", line)
    ]
    if player_rows:
        return len(player_rows)

    raise RconError(f"could not parse #players response: {normalized!r}")


def query_rcon_player_count(
    host: str,
    port: int,
    password: str,
    timeout: float,
    command: str,
) -> tuple[int, int]:
    """Return (players, max_players) from Reforger RCON `#players` output."""
    if not password:
        raise RconError("RCON_PASSWORD is required")

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        sock.sendto(battleye_packet(b"\x00" + password.encode()), (host, port))
        response, _ = sock.recvfrom(4096)
        payload = battleye_payload(response)
        if len(payload) < 2 or payload[0] != 0x00 or payload[1] != 0x01:
            raise RconError("RCON login failed")

        sequence = 0
        sock.sendto(
            battleye_packet(b"\x01" + bytes([sequence]) + command.encode()),
            (host, port),
        )

        deadline = time.monotonic() + timeout
        chunks: list[str] = []
        while time.monotonic() < deadline:
            response, addr = sock.recvfrom(4096)
            payload = battleye_payload(response)

            if len(payload) >= 2 and payload[0] == 0x02:
                sock.sendto(battleye_packet(b"\x02" + payload[1:2]), addr)
                continue

            if len(payload) >= 2 and payload[0] == 0x01 and payload[1] == sequence:
                chunks.append(payload[2:].decode("utf-8", errors="replace"))
                break

        players = parse_rcon_player_count("\n".join(chunks))
        return players, 0


def player_count_sources(value: str) -> list[str]:
    """Return an ordered list of player-count sources to try."""
    sources = [
        source.strip().lower()
        for source in re.split(r"[,\s]+", value)
        if source.strip()
    ]
    if sources == ["auto"]:
        return ["rcon", "a2s"]
    if not sources:
        raise ValueError("PLAYER_COUNT_SOURCE cannot be empty")

    supported = {"rcon", "a2s"}
    unsupported = [source for source in sources if source not in supported]
    if unsupported:
        raise ValueError(f"unsupported PLAYER_COUNT_SOURCE={','.join(unsupported)!r}")
    return sources


def query_configured_player_count(
    sources: list[str],
    a2s_host: str,
    a2s_port: int,
    rcon_host: str,
    rcon_port: int,
    rcon_password: str,
    timeout: float,
    rcon_command: str,
) -> tuple[int, int, str]:
    errors: list[str] = []

    for source in sources:
        try:
            if source == "rcon":
                players, max_players = query_rcon_player_count(
                    rcon_host,
                    rcon_port,
                    rcon_password,
                    timeout,
                    rcon_command,
                )
            elif source == "a2s":
                players, max_players = query_player_count(a2s_host, a2s_port, timeout)
            else:
                raise ValueError(f"unsupported PLAYER_COUNT_SOURCE={source!r}")
        except Exception as exc:  # noqa: BLE001 - try the next configured source
            logging.warning("player count query via %s failed: %s", source, exc)
            errors.append(f"{source}: {exc}")
            continue

        return players, max_players, source

    raise RuntimeError(f"all player count sources failed ({'; '.join(errors)})")


def main() -> int:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(message)s",
    )

    sources = player_count_sources(os.getenv("PLAYER_COUNT_SOURCE", "a2s"))
    a2s_host = os.getenv("A2S_HOST", "127.0.0.1")
    a2s_port = int(os.getenv("A2S_PORT", "17777"))
    rcon_host = os.getenv("RCON_HOST", "127.0.0.1")
    rcon_port = int(os.getenv("RCON_PORT", "19999"))
    rcon_password = os.getenv("RCON_PASSWORD", "")
    rcon_command = os.getenv("RCON_COMMAND", "#players")
    timeout = float(os.getenv("QUERY_TIMEOUT_SECONDS", "5"))
    check_interval = int(os.getenv("CHECK_INTERVAL_SECONDS", "60"))
    idle_seconds = int(os.getenv("IDLE_SECONDS", "1800"))
    startup_grace_seconds = int(os.getenv("STARTUP_GRACE_SECONDS", "600"))
    idle_on_query_failure = env_bool("IDLE_ON_QUERY_FAILURE", False)
    dry_run = env_bool("DRY_RUN", False)
    shutdown_command = os.getenv("SHUTDOWN_COMMAND", "/sbin/shutdown -h now")

    idle_started_at: float | None = None
    started_at = time.monotonic()

    logging.info(
        "watching player count via %s; idle threshold=%ss; interval=%ss",
        ",".join(sources),
        idle_seconds,
        check_interval,
    )

    while True:
        now = time.monotonic()
        in_startup_grace = now - started_at < startup_grace_seconds

        try:
            players, max_players, source = query_configured_player_count(
                sources,
                a2s_host,
                a2s_port,
                rcon_host,
                rcon_port,
                rcon_password,
                timeout,
                rcon_command,
            )
            logging.info("player count via %s: %s/%s", source, players, max_players)
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
