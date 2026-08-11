# Virtual gateway TDD evidence

## Journeys

- A developer can run and open a local virtual solar plant independently of Aelora.
- They can add arrays and change weather, time, load, efficiency, shading, soiling, grid availability, and device controls.
- Turning communications off preserves the device's last telemetry time and makes only that device offline.
- Stopping operation while communications remain on reports an online `STOPPED` or `FAULT` device.
- The simulation carries battery state, clips at inverter capacity, and always obeys `pv + battery + grid = load`.
- The gateway enrolls once, uses bearer authentication, buffers failed batches in SQLite, and replays them in sequence.
- Heartbeats keep gateway-process health current while telemetry publishing is paused.
- A pending credential can be applied locally without being echoed, then promoted through a real authenticated request.
- An operator can inspect the exact outbound method, path, headers, and body with bearer credentials redacted.
- Timed scenarios restore the previous plant automatically, including while telemetry is paused.
- SunSpec and Fronius fixtures normalize into the same canonical hardware units and sign conventions.

## RED/GREEN evidence

- RED checkpoint: `cb86144` (`test(gateway): define virtual plant and publishing contracts`). A compile-time import failed because the package and engine did not yet exist. GREEN: `9503656`.
- RED checkpoint: `31ef32b` (`test(gateway): define heartbeat scenarios and adapter contracts`). The heartbeat, credential, preview, scenario, and adapter contracts did not exist. GREEN: `5099584`.
- RED checkpoint: `35a3650` (`test(gateway): expire scenarios during heartbeat`). An expired outage stayed active while telemetry was paused. GREEN: `692187b`.

## Test specification

| Guarantee | Test file | Type | Result |
|---|---|---|---|
| Rain reduces PV and inverter rating clips AC output | `tests/test_engine.py` | Unit | PASS |
| Adding an array increases available generation | `tests/test_engine.py` | Unit | PASS |
| Communications and operation are independent | `tests/test_engine.py` | Unit | PASS |
| Offline communications retain last telemetry time | `tests/test_engine.py` | Unit | PASS |
| Every snapshot obeys Aelora's power sign convention | `tests/test_engine.py` | Unit | PASS |
| Local API adds arrays and changes weather | `tests/test_api.py` | Integration | PASS |
| Local API controls communications without stopping physical generation | `tests/test_api.py` | Integration | PASS |
| Publishing can be paused and interval changed | `tests/test_api.py` | Integration | PASS |
| Rotated credentials are stored without being echoed | `tests/test_api.py` | Integration | PASS |
| Exact outbound requests redact bearer credentials | `tests/test_api.py` | Integration | PASS |
| Timed scenarios start, stop, and restore state | `tests/test_api.py` | Integration | PASS |
| Enrollment stores the returned gateway identity and credential locally | `tests/test_publisher.py` | Unit/integration | PASS |
| Failed batches persist and replay with bearer authentication | `tests/test_publisher.py` | Unit/integration | PASS |
| Heartbeats continue while telemetry publishing is paused | `tests/test_publisher.py` | Unit/integration | PASS |
| Heartbeats restore expired scenarios while telemetry is paused | `tests/test_publisher.py` | Regression | PASS |
| Fronius and SunSpec fixtures normalize to the same units/signs | `tests/test_adapters.py` | Contract | PASS |
| SunSpec scale factors are applied before normalization | `tests/test_adapters.py` | Unit | PASS |

## Final gates

- `python -m ruff check src tests` → PASS.
- `python -m pytest --cov=aelora_virtual_gateway --cov-report=term-missing --cov-fail-under=80` → 17 passed; 88.5% total coverage.
- `python -m compileall -q src tests` → PASS.
- `pip-audit --skip-editable` → PASS: no known vulnerabilities; the editable local project is correctly excluded from the public-package lookup.
- Local smoke test on `http://127.0.0.1:4100/api/state` → PASS.
- End-to-end Aelora enrollment, heartbeat, credential rotation/promotion, persisted batch, timed grid-outage scenario, and restoration → PASS.

One non-failing warning comes from FastAPI's current `TestClient` compatibility layer suggesting a future Starlette transport dependency. It does not affect runtime behavior.
