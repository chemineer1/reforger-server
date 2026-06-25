import base64
import json
import os
import socket
import struct
from dataclasses import dataclass

import boto3
from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey


INTERACTION_PING = 1
INTERACTION_APPLICATION_COMMAND = 2
RESPONSE_PONG = 1
RESPONSE_CHANNEL_MESSAGE_WITH_SOURCE = 4
EPHEMERAL = 1 << 6
A2S_QUERY = b"\xff\xff\xff\xffTSource Engine Query\x00"
S2A_INFO = 0x49
S2A_CHALLENGE = 0x41

ec2 = boto3.client("ec2")


class A2SQueryError(RuntimeError):
    """Raised when a live A2S query cannot return usable server info."""


@dataclass(frozen=True)
class A2SInfo:
    name: str
    map_name: str
    players: int
    max_players: int


def response(status_code, payload):
    return {
        "statusCode": status_code,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(payload),
    }


def interaction_message(content):
    return response(
        200,
        {
            "type": RESPONSE_CHANNEL_MESSAGE_WITH_SOURCE,
            "data": {
                "content": content,
                "flags": EPHEMERAL,
            },
        },
    )


def header(headers, name):
    for key, value in (headers or {}).items():
        if key.lower() == name.lower():
            return value
    return None


def raw_body(event):
    body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        return base64.b64decode(body)
    return body.encode("utf-8")


def verify_discord_request(event):
    public_key = os.environ.get("DISCORD_PUBLIC_KEY")
    if not public_key:
        raise RuntimeError("DISCORD_PUBLIC_KEY is not set")

    signature = header(event.get("headers"), "x-signature-ed25519")
    timestamp = header(event.get("headers"), "x-signature-timestamp")
    if not signature or not timestamp:
        return False

    message = timestamp.encode("utf-8") + raw_body(event)
    try:
        VerifyKey(bytes.fromhex(public_key)).verify(message, bytes.fromhex(signature))
        return True
    except BadSignatureError:
        return False


def allowed_user_ids():
    raw_ids = os.environ.get("DISCORD_ALLOWED_USER_IDS", "")
    return {value.strip() for value in raw_ids.split(",") if value.strip()}


def is_authorized(interaction):
    allowed = allowed_user_ids()
    if not allowed:
        return True

    user_id = (
        interaction.get("member", {}).get("user", {}).get("id")
        or interaction.get("user", {}).get("id")
    )
    return user_id in allowed


def instance_id():
    value = os.environ.get("EC2_INSTANCE_ID")
    if not value:
        raise RuntimeError("EC2_INSTANCE_ID is not set")
    return value


def env_int(name, default):
    value = os.environ.get(name)
    if value is None:
        return default
    return int(value)


def env_float(name, default):
    value = os.environ.get(name)
    if value is None:
        return default
    return float(value)


def describe_instance():
    result = ec2.describe_instances(InstanceIds=[instance_id()])
    reservations = result.get("Reservations", [])
    instances = reservations[0].get("Instances", []) if reservations else []
    if not instances:
        raise RuntimeError(f"EC2 instance not found: {instance_id()}")

    instance = instances[0]
    return {
        "id": instance.get("InstanceId"),
        "state": instance.get("State", {}).get("Name", "unknown"),
        "public_ip": instance.get("PublicIpAddress", ""),
        "type": instance.get("InstanceType", ""),
    }


def start_server():
    before = describe_instance()
    if before["state"] in {"running", "pending"}:
        return f"Reforger EC2 instance is already {before['state']}."

    ec2.start_instances(InstanceIds=[instance_id()])
    return "Starting Reforger EC2 instance."


def stop_server():
    before = describe_instance()
    if before["state"] in {"stopped", "stopping"}:
        return f"Reforger EC2 instance is already {before['state']}."

    ec2.stop_instances(InstanceIds=[instance_id()])
    return "Stopping Reforger EC2 instance."


def read_c_string(payload, offset):
    try:
        end = payload.index(0, offset)
    except ValueError as error:
        raise A2SQueryError("missing string terminator") from error
    return payload[offset:end].decode("utf-8", errors="replace"), end + 1


def parse_a2s_info_response(response):
    if not response.startswith(b"\xff\xff\xff\xff"):
        raise A2SQueryError("unsupported split or malformed A2S response")

    payload = response[4:]
    if not payload or payload[0] != S2A_INFO:
        raise A2SQueryError("unexpected A2S response type")

    offset = 2
    try:
        name, offset = read_c_string(payload, offset)
        map_name, offset = read_c_string(payload, offset)
        _, offset = read_c_string(payload, offset)  # folder
        _, offset = read_c_string(payload, offset)  # game
        offset += struct.calcsize("<H")  # Steam app ID
        players = payload[offset]
        max_players = payload[offset + 1]
    except IndexError as error:
        raise A2SQueryError("truncated A2S response") from error

    return A2SInfo(
        name=name,
        map_name=map_name,
        players=players,
        max_players=max_players,
    )


def query_a2s_info(host, port, timeout):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(timeout)
            sock.sendto(A2S_QUERY, (host, port))
            response, _ = sock.recvfrom(4096)

            if not response.startswith(b"\xff\xff\xff\xff"):
                raise A2SQueryError("unsupported split or malformed A2S response")

            payload = response[4:]
            if payload and payload[0] == S2A_CHALLENGE:
                if len(payload) < 5:
                    raise A2SQueryError("malformed A2S challenge response")
                sock.sendto(A2S_QUERY + payload[1:5], (host, port))
                response, _ = sock.recvfrom(4096)

            return parse_a2s_info_response(response)
    except (OSError, socket.timeout) as error:
        raise A2SQueryError("A2S query failed") from error


def server_status():
    instance = describe_instance()
    lines = [f"Reforger EC2 instance is {instance['state']}."]

    if instance["state"] == "running" and instance["public_ip"]:
        try:
            server = query_a2s_info(
                instance["public_ip"],
                env_int("A2S_PORT", 17777),
                env_float("A2S_TIMEOUT_SECONDS", 3),
            )
        except A2SQueryError:
            lines.append(f"Public IP: {instance['public_ip']}")
            lines.append("Game query: unavailable")
        else:
            lines.append(f"Server: {server.name}")
            lines.append(f"Players: {server.players}/{server.max_players}")
            if server.map_name:
                lines.append(f"Map: {server.map_name}")
            lines.append(f"Public IP: {instance['public_ip']}")
    elif instance["public_ip"]:
        lines.append(f"Public IP: {instance['public_ip']}")

    return "\n".join(lines)


def subcommand_name(interaction):
    options = interaction.get("data", {}).get("options") or []
    if options:
        return options[0].get("name")
    return interaction.get("data", {}).get("name")


def lambda_handler(event, context):
    try:
        if not verify_discord_request(event):
            return response(401, {"error": "invalid request signature"})

        interaction = json.loads(raw_body(event).decode("utf-8"))

        if interaction.get("type") == INTERACTION_PING:
            return response(200, {"type": RESPONSE_PONG})

        if interaction.get("type") != INTERACTION_APPLICATION_COMMAND:
            return interaction_message("Unsupported interaction type.")

        if not is_authorized(interaction):
            return interaction_message("You are not allowed to control this server.")

        command = subcommand_name(interaction)
        if command == "start":
            return interaction_message(start_server())
        if command == "stop":
            return interaction_message(stop_server())
        if command == "status":
            return interaction_message(server_status())

        return interaction_message("Unknown Reforger command.")
    except Exception as error:
        print(f"command failed: {error}", flush=True)
        return interaction_message(f"Command failed: {error}")
