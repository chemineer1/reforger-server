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
cd deploy/discord-lambda
sam build --beta-features
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
uv run register_commands.py
```

Omit `DISCORD_GUILD_ID` to register globally.

## Permissions

### SAM Deployer

The AWS identity running `sam deploy` needs permission to manage the
CloudFormation stack and upload build artifacts to S3. SAM uses S3 as a
deployment staging bucket for the Lambda ZIP, even though the Lambda does not
use S3 at runtime.

At minimum, the deployer needs access to:

```text
cloudformation:*
s3:CreateBucket
s3:GetObject
s3:PutObject
s3:DeleteObject
s3:ListBucket
iam:*
lambda:*
```

If using `sam deploy --resolve-s3`, SAM creates and manages a helper stack named
`aws-sam-cli-managed-default` for its artifact bucket. If that stack is stuck in
`ROLLBACK_COMPLETE`, delete it and rerun `sam deploy --resolve-s3`.

### Lambda Runtime Role

The Lambda role is limited to:

```text
ec2:DescribeInstances
ec2:StartInstances
ec2:StopInstances
```

`StartInstances` and `StopInstances` are scoped to the configured EC2 instance.

## Notes

The commands only control EC2 state. The EC2 host relies on Docker's restart
policy to start the existing Compose container when Docker starts, and the idle
shutdown service still stops the host after the configured zero-player window.
