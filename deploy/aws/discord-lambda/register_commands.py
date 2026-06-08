#!/usr/bin/env python3
import json
import os
import sys
import urllib.error
import urllib.request


COMMANDS = [
    {
        "name": "reforger",
        "description": "Control the Arma Reforger EC2 server.",
        "options": [
            {
                "type": 1,
                "name": "start",
                "description": "Start the EC2 instance.",
            },
            {
                "type": 1,
                "name": "stop",
                "description": "Stop the EC2 instance.",
            },
            {
                "type": 1,
                "name": "status",
                "description": "Show EC2 instance state.",
            },
        ],
    }
]


def main():
    app_id = os.environ.get("DISCORD_APP_ID")
    bot_token = os.environ.get("DISCORD_BOT_TOKEN")
    guild_id = os.environ.get("DISCORD_GUILD_ID")

    if not app_id or not bot_token:
        print("DISCORD_APP_ID and DISCORD_BOT_TOKEN are required.", file=sys.stderr)
        return 1

    route = (
        f"/applications/{app_id}/guilds/{guild_id}/commands"
        if guild_id
        else f"/applications/{app_id}/commands"
    )
    request = urllib.request.Request(
        f"https://discord.com/api/v10{route}",
        data=json.dumps(COMMANDS).encode("utf-8"),
        method="PUT",
        headers={
            "authorization": f"Bot {bot_token}",
            "content-type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            print(json.dumps(json.loads(response.read()), indent=2))
            return 0
    except urllib.error.HTTPError as error:
        print(error.read().decode("utf-8", errors="replace"), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
