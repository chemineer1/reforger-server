# Discord Slash Commands

This Python Lambda gives a Discord app slash commands for the EC2 instance that runs
the Reforger server:

```text
/reforger start
/reforger stop
/reforger status
```

`/reforger status` describes the EC2 instance and, when the instance is
running, queries the game server's public Steam A2S endpoint on UDP `17777` for
the live server name, map, and player count.

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

## Test And Deploy Lambda

Run the Lambda tests before deploying:

```sh
cd deploy/discord-lambda
uv run pytest
```

For the first deployment, build and deploy with AWS SAM:

```sh
cd deploy/discord-lambda
sam build --beta-features
sam deploy --guided \
  --parameter-overrides \
    InstanceId=i-xxxxxxxxxxxxxxxxx \
    DiscordPublicKey=your-discord-public-key
```

For later deployments to the existing stack, reuse the saved stack settings or
pass them explicitly:

```sh
cd deploy/discord-lambda
sam build --beta-features
sam deploy \
  --stack-name reforger-discord-lambda \
  --resolve-s3 \
  --capabilities CAPABILITY_IAM \
  --no-confirm-changeset \
  --no-fail-on-empty-changeset \
  --region us-east-2 \
  --parameter-overrides \
    InstanceId=i-0741f424a422aeb18 \
    DiscordPublicKey="$PUBLIC_KEY"
```

Leave `DiscordAllowedUserIds` empty if the command only exists in your private
Discord server and you are comfortable using Discord server access as the
control boundary. If you use that parameter, include it in
`--parameter-overrides` on repeat deploys so the stack keeps the intended
authorization list.

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

The start and stop commands only control EC2 state. The EC2 host relies on
Docker's restart policy to start the existing Compose container when Docker
starts, and the idle shutdown service still stops the host after the configured
zero-player window.

The status command also sends a live UDP query from Lambda to the instance's
public IP on the configured A2S port. Keep `17777/udp` open in the instance
security group for Steam A2S queries. If the EC2 instance is running but the
game server is still booting or the A2S query is unreachable, the command keeps
the EC2 status response and shows `Game query: unavailable`.
