import json
import os
import struct
import sys
from pathlib import Path

import pytest


os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_EC2_METADATA_DISABLED", "true")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app  # noqa: E402


class LambdaContext:
    aws_request_id = "test-request-123"


def a2s_response(name="Reforger Test", map_name="Everon", players=0, max_players=8):
    payload = bytearray([app.S2A_INFO, 17])
    payload.extend(name.encode("utf-8") + b"\x00")
    payload.extend(map_name.encode("utf-8") + b"\x00")
    payload.extend(b"reforger\x00")
    payload.extend(b"Arma Reforger\x00")
    payload.extend(struct.pack("<H", 0))
    payload.extend(bytes([players, max_players, 0]))
    return b"\xff\xff\xff\xff" + bytes(payload)


def interaction_content(result):
    return json.loads(result["body"])["data"]["content"]


def test_parse_a2s_info_response_reads_name_map_and_players():
    result = app.parse_a2s_info_response(
        a2s_response(name="Ruben's Server", map_name="Arland", players=0, max_players=8)
    )

    assert result == app.A2SInfo(
        name="Ruben's Server",
        map_name="Arland",
        players=0,
        max_players=8,
    )


def test_parse_a2s_info_response_rejects_malformed_packet():
    with pytest.raises(app.A2SQueryError):
        app.parse_a2s_info_response(b"not-a-source-packet")


def test_server_status_skips_a2s_when_instance_is_stopped(monkeypatch):
    monkeypatch.setattr(
        app,
        "describe_instance",
        lambda: {
            "id": "i-test",
            "state": "stopped",
            "public_ip": "",
            "type": "t3.small",
        },
    )

    def fail_query(host, port, timeout):
        raise AssertionError("A2S should not be queried for a stopped instance")

    monkeypatch.setattr(app, "query_a2s_info", fail_query)

    assert app.server_status() == "Reforger EC2 instance is stopped."


def test_server_status_includes_live_game_status(monkeypatch):
    monkeypatch.setattr(
        app,
        "describe_instance",
        lambda: {
            "id": "i-test",
            "state": "running",
            "public_ip": "203.0.113.10",
            "type": "t3.small",
        },
    )

    def query(host, port, timeout):
        assert host == "203.0.113.10"
        assert port == 17777
        assert timeout == 3
        return app.A2SInfo(
            name="Ruben's Server",
            map_name="Everon",
            players=2,
            max_players=8,
        )

    monkeypatch.setattr(app, "query_a2s_info", query)

    assert app.server_status() == "\n".join(
        [
            "Reforger EC2 instance is running.",
            "Server: Ruben's Server",
            "Players: 2/8",
            "Map: Everon",
            "Public IP: 203.0.113.10",
        ]
    )


def test_server_status_hides_a2s_errors(monkeypatch):
    monkeypatch.setattr(
        app,
        "describe_instance",
        lambda: {
            "id": "i-test",
            "state": "running",
            "public_ip": "203.0.113.10",
            "type": "t3.small",
        },
    )

    def timeout(host, port, query_timeout):
        raise app.A2SQueryError("socket timeout details")

    monkeypatch.setattr(app, "query_a2s_info", timeout)

    assert app.server_status() == "\n".join(
        [
            "Reforger EC2 instance is running.",
            "Public IP: 203.0.113.10",
            "Game query: unavailable",
        ]
    )


def test_interaction_message_disables_allowed_mentions():
    result = app.interaction_message("hello @everyone")
    body = json.loads(result["body"])

    assert body["data"]["flags"] == app.EPHEMERAL
    assert body["data"]["allowed_mentions"] == {"parse": []}


def test_lambda_handler_hides_raw_top_level_exception(monkeypatch):
    monkeypatch.setattr(app, "verify_discord_request", lambda event: True)

    def fail_status():
        raise RuntimeError("secret failure details")

    monkeypatch.setattr(app, "server_status", fail_status)

    result = app.lambda_handler(
        {
            "body": json.dumps(
                {
                    "type": app.INTERACTION_APPLICATION_COMMAND,
                    "data": {"options": [{"name": "status"}]},
                }
            ),
            "headers": {},
        },
        LambdaContext(),
    )

    content = interaction_content(result)
    assert content == "Command failed. Check Lambda logs for request test-request-123."
    assert "secret failure details" not in content


def test_server_status_sanitizes_dynamic_game_fields(monkeypatch):
    monkeypatch.setattr(
        app,
        "describe_instance",
        lambda: {
            "id": "i-test",
            "state": "running",
            "public_ip": "203.0.113.10",
            "type": "t3.small",
        },
    )
    monkeypatch.setattr(
        app,
        "query_a2s_info",
        lambda host, port, timeout: app.A2SInfo(
            name="Bad\nName @everyone",
            map_name="\t<@123456789>",
            players=1,
            max_players=8,
        ),
    )

    result = app.server_status()

    assert "Server: Bad Name [at]everyone" in result
    assert "Map: <[at]123456789>" in result
    assert "@everyone" not in result
    assert "<@123456789>" not in result


def test_safe_display_caps_length_and_uses_fallback():
    assert app.safe_display("\n\t") == "unknown"
    assert app.safe_display("x" * 200) == ("x" * 117) + "..."
