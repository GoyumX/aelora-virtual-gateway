# Virtual gateway TDD evidence

## Journeys

- A developer can run and open a local virtual solar plant independently of Aelora.
- They can add arrays and change weather, time, load, efficiency, shading, soiling, grid availability, and device controls.
- Turning communications off preserves the device's last telemetry time and makes only that device offline.
- Stopping operation while communications remain on reports an online `STOPPED` or `FAULT` device.
- The simulation carries battery state, clips at inverter capacity, and always obeys `pv + battery + grid = load`.
- The gateway enrolls once, uses bearer authentication, buffers failed batches in SQLite, and replays them in sequence.

## RED/GREEN evidence

- RED checkpoint: `cb86144` (`test(gateway): define virtual plant and publishing contracts`). A compile-time import failed because the package and engine did not yet exist.
- GREEN implementation: source in `src/aelora_virtual_gateway`, verified by the commands below.

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
| Enrollment stores the returned gateway identity and credential locally | `tests/test_publisher.py` | Unit/integration | PASS |
| Failed batches persist and replay with bearer authentication | `tests/test_publisher.py` | Unit/integration | PASS |

## Final gates

- `python -m ruff check src tests` → PASS.
- `python -m pytest --cov=aelora_virtual_gateway --cov-report=term-missing --cov-fail-under=80` → 10 passed; 83.9% total coverage.
- `python -m compileall -q src tests` → PASS.
- Local smoke test on `http://127.0.0.1:4100/api/state` → PASS.
- End-to-end Aelora enrollment and persisted batch → PASS.

One non-failing warning comes from FastAPI's current `TestClient` compatibility layer suggesting a future Starlette transport dependency. It does not affect runtime behavior.
