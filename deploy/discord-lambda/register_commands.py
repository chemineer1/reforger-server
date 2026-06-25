import os
import requests


COMMANDS ={
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
            "description": "Show the status of the EC2 instance.",
        },
    ],
}


app_id = os.environ.get("DISCORD_APP_ID")
bot_token = os.environ.get("DISCORD_BOT_TOKEN")
guild_id = os.environ.get("DISCORD_GUILD_ID")

url = f"https://discord.com/api/v10/applications/{app_id}/guilds/{guild_id}/commands"

headers = {
    "Authorization": f"Bot {bot_token}"
}

r = requests.post(url, headers=headers, json=COMMANDS)
print(f"Status code: {r.status_code}")
print(f"Response: {r.text}")
