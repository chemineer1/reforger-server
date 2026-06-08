# Discord Slash Commands

This Python Lambda gives a Discord app slash commands for the EC2 instance that runs
the Reforger server:

```text
/reforger start
/reforger stop
/reforger status
```

The Lambda uses a Function URL as the Discord Interactions Endpoint. Discord
sends signed interaction requests with `X-Signature-Ed25519` and
`X-Signature-Timestamp`; the handler verifies those headers before doing any EC2
work.

## Discord App

Create a Discord application and bot in the Discord Developer Portal.

Collect these values:

```text
Application ID
Bot token
Public key
Guild ID, optional but recommended while testing
Allowed Discord user IDs, optional
```

## Deploy Lambda

Build and deploy with AWS SAM:

```sh
cd deploy/aws/discord-lambda
sam build
sam deploy --guided \
  --parameter-overrides \
    InstanceId=i-xxxxxxxxxxxxxxxxx \
    DiscordPublicKey=your-discord-public-key
```

Leave `DiscordAllowedUserIds` empty if the command only exists in your private
Discord server and you are comfortable using Discord server access as the
control boundary.

Use the stack output `DiscordInteractionsUrl` as the Discord app's
Interactions Endpoint URL.

## Register Slash Command

For fast iteration, register the command to one guild:

```sh
export DISCORD_APP_ID=your-application-id
export DISCORD_BOT_TOKEN=your-bot-token
export DISCORD_GUILD_ID=your-test-guild-id
python3 register_commands.py
```

Omit `DISCORD_GUILD_ID` to register globally.

## Permissions

The Lambda role is limited to:

```text
ec2:DescribeInstances
ec2:StartInstances
ec2:StopInstances
```

`StartInstances` and `StopInstances` are scoped to the configured EC2 instance.

## Notes

The commands only control EC2 state. The EC2 host still uses systemd to start
Docker Compose when it boots, and the idle shutdown service still stops the host
after the configured zero-player window.
