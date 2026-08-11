# Aelora Virtual Gateway

This is the separately runnable Python virtual solar-site gateway for Aelora. It is intentionally a sibling project with its own Git history—not a package, API route, or background task inside the Next.js application.

It provides:

- a local control console at `http://localhost:4100`;
- virtual arrays, inverter, battery, grid, load meter, and weather sensor;
- independent communications and operating controls;
- manual weather, time, load, efficiency, shading, soiling, grid-outage, and publishing controls;
- timed cloud, rain, dirty-array, shade, inverter, battery, and grid-outage scenarios with automatic restoration;
- carried battery state of charge, inverter clipping, and balanced site power flow;
- one-time enrollment with Aelora and a long-lived bearer credential stored only in the local SQLite database;
- a separate heartbeat stream that stays active when telemetry publishing is paused;
- safe local credential rotation and an exact outbound request preview with bearer values redacted;
- fixture-backed SunSpec and Fronius normalizers that produce the same canonical hardware telemetry shape;
- monotonic sequences, UUID batch IDs, idempotent delivery, and a persistent retry buffer.

## Run the prepared local project

The current workspace already has its isolated `.venv` prepared:

```powershell
cd C:\Users\GoYuM\Documents\ChatGPT\Aelora\Project\aelora-virtual-gateway
.\scripts\start.ps1
```

Open [http://localhost:4100](http://localhost:4100).

## Fresh setup

Install Python 3.11 or newer, then:

```powershell
.\scripts\setup.ps1
.\scripts\start.ps1
```

The server binds to `127.0.0.1` by default. Copy `.env.example` to `.env` only if you need to change Aelora's URL, the local port, or the SQLite path.

## Connect it to Aelora

1. Start PostgreSQL and Aelora on `http://localhost:3000`.
2. Sign in to Aelora and open **System Configuration**.
3. Under **Site gateways**, choose **Create enrollment**.
4. Copy the one-time token. It expires in 30 minutes and Aelora stores only its hash.
5. Open the gateway console at `http://localhost:4100`, paste the token under **Aelora enrollment**, and enroll.
6. Click **Publish now** or leave the 30-second publisher running.
7. Open Aelora Dashboard or Live Monitoring. Those pages now display only persisted gateway readings.

When Aelora rotates a credential, paste the newly issued credential into **Rotated credential** in the local console. The old credential continues working until the gateway proves possession of the pending credential; that first accepted heartbeat or telemetry request promotes the new credential and invalidates the old one.

## What each control means

| Console action | Result in Aelora |
|---|---|
| Close the gateway process | Gateway and devices age from online to stale and then offline; last readings stay visible |
| Pause publishing | Telemetry becomes stale while independent heartbeats keep the gateway itself online |
| Turn a device's communications off | Only that device reports offline; its last telemetry timestamp is preserved |
| Stop device operation with communications on | Device remains online and reports `STOPPED` or `FAULT` |
| Select rain/night or add shade/soiling | Device remains online with legitimately reduced production |
| Trigger grid outage | Grid remains communicative but reports a fault, zero voltage, and zero grid flow |
| Start a timed scenario | The selected condition applies for the requested duration and then restores the previous plant state, even while telemetry is paused |

## Verification

```powershell
.\.venv\Scripts\python.exe -m ruff check src tests
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m pytest --cov=aelora_virtual_gateway --cov-fail-under=80
.\.venv\Scripts\pip-audit.exe --skip-editable
```

Current result: 17 tests pass, total Python coverage is 88.5%, lint and bytecode compilation pass, and the dependency audit finds no known vulnerabilities.

## Real-equipment transition

The public Aelora API does not need to change for real hardware. The included SunSpec and Fronius JSON fixtures prove the normalization boundary without claiming a live device connection. The next hardware step is to add read-only transports that poll actual SunSpec/Modbus TCP registers or a vendor-local endpoint, then pass their responses through the same normalizers. The edge process continues sending the same versioned JSON batches over outbound HTTPS. Passive panels themselves normally have no network identity; map Aelora array health to actual reporting MPPT/string/optimizer/microinverter channels when the hardware exposes them.
