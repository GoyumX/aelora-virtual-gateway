# Host the Aelora virtual gateway on Railway for a showcase

This is an optional demonstration deployment. It gives the virtual gateway its
own HTTPS control-console URL while it continues to send simulated telemetry to
the deployed Aelora web application. It does not replace the future physical
gateway, which should run beside the solar equipment.

## Result

Your existing Railway project will contain one additional service and volume:

```text
aelora-demo-gateway        Public HTTPS console + background simulator
└── aelora-demo-data       SQLite state mounted at /app/data
```

The browser-to-console connection is HTTPS and protected with a separate demo
username and password. Aelora enrollment still creates the independent gateway
credential used for telemetry and heartbeats.

## Before starting

Confirm all of these first:

- `aelora-web` is online and `https://YOUR-AELORA-DOMAIN/api/health` returns
  `status: ok`;
- the latest `dev` branch of
  `https://github.com/GoyumX/aelora-virtual-gateway` is pushed;
- the gateway repository contains `Dockerfile`, `docker-entrypoint.sh`, and the
  public-demo environment variables documented below;
- no real password, token, `.env`, or `gateway.db` file is committed to GitHub.

## Step 1 — Create a dedicated console password

Open Windows Command Prompt and run:

```bat
node -e "console.log(require('crypto').randomBytes(32).toString('base64url'))"
```

Save the result in your password manager as **Aelora demo gateway console**.
Do not reuse the Aelora admin password, Better Auth secret, ML token, weather
secret, or gateway enrollment token.

Choose a simple separate username for the browser prompt, for example
`goyum-demo`. Do not place either value in a local `.env.example` file or Git.

## Step 2 — Add the gateway service

1. Open the same **Aelora** project in Railway.
2. Select **New → GitHub Repo**.
3. Choose `GoyumX/aelora-virtual-gateway`.
4. Select the `dev` branch for the first deployment.
5. Rename the service exactly to `aelora-demo-gateway`.
6. Leave Root Directory empty because the Dockerfile is at the repository root.
7. Do not add a custom Build Command or Start Command. Railway will detect the
   root `Dockerfile` and run its `CMD`.

The first deploy may fail before variables are added. That is expected; finish
the configuration and redeploy.

## Step 3 — Add the Railway variables

Open **aelora-demo-gateway → Variables → Raw Editor** and paste this template:

```text
AELORA_BASE_URL=http://${{aelora-web.RAILWAY_PRIVATE_DOMAIN}}:3000
AELORA_GATEWAY_HOST=0.0.0.0
AELORA_GATEWAY_DB=/app/data/gateway.db
AELORA_GATEWAY_RELOAD=false
AELORA_GATEWAY_PUBLIC_DEMO=true
AELORA_GATEWAY_CONSOLE_USERNAME=REPLACE_WITH_YOUR_DEMO_USERNAME
AELORA_GATEWAY_CONSOLE_PASSWORD=REPLACE_WITH_YOUR_RANDOM_DEMO_PASSWORD
```

Replace only the final two values. Keep the Railway reference expression for
`AELORA_BASE_URL` exactly as shown. Do not add Markdown brackets, quotes, or a
trailing slash.

Do not manually create `PORT`. Railway injects it, and the gateway now gives
that value priority over its local port setting.

## Step 4 — Attach persistent storage

1. On the Railway project canvas, right-click or choose **New → Volume**.
2. Attach the volume to `aelora-demo-gateway`.
3. Name it `aelora-demo-data`.
4. Set its mount path to exactly `/app/data`.

The SQLite file at `/app/data/gateway.db` contains the simulated plant,
enrollment credential, delivery sequence, and retry buffer. Without the volume,
a redeploy would create a new gateway identity.

The included container entrypoint fixes the mounted directory ownership, then
drops privileges to the unprivileged `aelora` user. Do not add
`RAILWAY_RUN_UID=0`.

## Step 5 — Configure health and runtime settings

Under **aelora-demo-gateway → Settings**:

1. Set **Healthcheck Path** to `/api/health`.
2. Set **Healthcheck Timeout** to `300` seconds.
3. Use one replica only. This demo has one SQLite database and one simulated
   site identity.
4. Set restart policy to **On Failure**, with 5 retries if Railway asks.
5. Disable **Serverless** for the presentation so the simulator and heartbeat
   loop stay warm and predictable.

`/api/health` intentionally remains public so Railway can receive HTTP 200.
The console, static assets, API state, enrollment, and every control endpoint
remain protected by the browser username and password.

## Step 6 — Create the public console URL

1. Open **Settings → Networking → Public Networking**.
2. Choose **Generate Domain**.
3. Do not type a custom target port unless Railway specifically asks; the
   gateway listens on Railway's injected `PORT`.
4. Copy the generated HTTPS URL, for example
   `https://aelora-demo-gateway-production.up.railway.app`.

Open the URL in a private/incognito browser window. The browser should show a
username/password prompt. Enter the two console values from Step 1. You should
then see the virtual gateway console.

Security checkpoint: if the console opens without a password prompt, remove the
public domain immediately and check that `AELORA_GATEWAY_PUBLIC_DEMO=true` is on
the gateway service—not on the ML or web service.

## Step 7 — Verify the deployment before enrollment

Open:

```text
https://YOUR-GATEWAY-DOMAIN/api/health
```

Expected result:

```json
{"status":"ok","version":"..."}
```

Then verify:

- the Railway deployment is **Active**;
- deployment logs show Uvicorn listening on `0.0.0.0` and Railway's port;
- the console shows arrays, inverter, battery, and grid;
- refreshing the page retains the simulated equipment;
- an incorrect browser password returns HTTP 401.

## Step 8 — Enroll the hosted gateway

1. Sign in to the deployed Aelora web application.
2. Open **System Configuration → Site gateways** for the demo site.
3. Create a one-time enrollment token. It expires after 30 minutes.
4. Open the hosted gateway console and authenticate at the browser prompt.
5. Paste the token under **Aelora enrollment** and enroll.
6. Set publishing to 30 or 60 seconds.
7. Choose **Publish now** once.
8. Return to Aelora Dashboard or Live Monitoring.

Within the configured freshness window, Aelora should show the gateway, arrays,
inverter, battery, and grid online. The dashboard should begin receiving new
timestamps and power values.

## Step 9 — Run the presentation demonstration

A reliable five-minute showcase sequence is:

1. Show the live Aelora Dashboard and current device-online indicators.
2. Open the gateway console in another tab and change cloud variability or
   household load range.
3. Return to Aelora and show the new telemetry arriving.
4. Start **Passing clouds** or **Grid outage** as a timed scenario.
5. Show the changed power flow or alert in Aelora.
6. Turn one array's communications off and explain that Aelora eventually marks
   only that source offline because its telemetry stopped.
7. Restore communications and show recovery.

Do not repeatedly click **Publish now**. The background loop already publishes
at the saved interval.

## Step 10 — After the showcase

For a private classroom demo you may leave the service running. For the safest
cleanup after a public event:

1. Remove the generated public domain, or stop the gateway service.
2. Rotate `AELORA_GATEWAY_CONSOLE_PASSWORD` before the next event.
3. Revoke/re-enroll the demo gateway from Aelora if the enrollment credential
   may have been exposed.
4. Keep the volume if you want to preserve the simulated site; delete it only if
   you intentionally want to erase the demo enrollment and state.

Never use the hosted demo gateway as evidence that real hardware is connected.
Its telemetry is explicitly simulated.

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| Healthcheck says service unavailable | The process is not listening on Railway's `PORT` or latest gateway code is not deployed | Confirm the service uses the latest `dev`, remove custom Start Command, and redeploy |
| Startup says public demo requires credentials | Username is empty, contains `:`, or password is under 16 characters | Correct the two console variables and redeploy |
| Console returns 401 repeatedly | Browser credentials do not match Railway variables | Use a private window, re-enter the exact username/password, or rotate them |
| SQLite says permission denied | Old image lacks the volume-aware entrypoint | Deploy the latest gateway commit containing `docker-entrypoint.sh`; do not set `RAILWAY_RUN_UID=0` |
| Gateway says Aelora cannot be reached | Web service name/reference or port is wrong | Keep `AELORA_BASE_URL=http://${{aelora-web.RAILWAY_PRIVATE_DOMAIN}}:3000` and confirm `aelora-web` is online |
| Gateway becomes new after redeploy | Volume is missing or mounted elsewhere | Attach one volume to this service at exactly `/app/data` |
| Devices remain offline | Publishing or device communications are disabled | Resume publishing, enable communications, and wait for the next interval |
| First public request is slow or returns 502 | Serverless/cold start is enabled | Disable Serverless for presentation use and redeploy |

## Official Railway references

- Dockerfiles: <https://docs.railway.com/builds/dockerfiles>
- Healthchecks and injected `PORT`: <https://docs.railway.com/deployments/healthchecks>
- Volumes: <https://docs.railway.com/volumes>
- Variables and service references: <https://docs.railway.com/variables/reference>
- Serverless mode: <https://docs.railway.com/deployments/serverless>
