# Virtual gateway TDD evidence

## Journeys

- A developer can run and open a local virtual solar plant independently of Aelora.
- The default simulation clock follows the host computer's current date, local time, and timezone; manual time remains available for previews.
- They can add arrays and change weather, cloud variability, fixed or ranged load, battery capacity/SoC/limits, grid signal variation, efficiency, shading, soiling, grid availability, and device controls.
- Seeded 30-second intervals vary PV, household demand, and grid signals as reproducible time-correlated curves without violating the site power balance.
- Turning communications off preserves the device's last telemetry time and makes only that device offline.
- Stopping operation while communications remain on reports an online `STOPPED` or `FAULT` device.
- The simulation carries battery state, clips at inverter capacity, and always obeys `pv + battery + grid = load`.
- The gateway enrolls once, uses bearer authentication, buffers failed batches in SQLite, and replays them in sequence.
- Resetting the virtual plant keeps enrollment, the monotonic sequence, and buffered batches, then creates a fresh measurement immediately.
- Heartbeats keep gateway-process health current while telemetry publishing is paused.
- Heartbeats synchronize the saved publishing cadence with Aelora's expected interval.
- A developer can replay one complete simulator hour through normal authenticated ingestion without mutating live plant state.
- A pending credential can be applied locally without being echoed, then promoted through a real authenticated request.
- An operator can inspect the exact outbound method, path, headers, and body with bearer credentials redacted.
- Timed scenarios restore the previous plant automatically, including while telemetry is paused.
- SunSpec and Fronius fixtures normalize into the same canonical hardware units and sign conventions.

## RED/GREEN evidence

- RED checkpoint: `cb86144` (`test(gateway): define virtual plant and publishing contracts`). A compile-time import failed because the package and engine did not yet exist. GREEN: `9503656`.
- RED checkpoint: `31ef32b` (`test(gateway): define heartbeat scenarios and adapter contracts`). The heartbeat, credential, preview, scenario, and adapter contracts did not exist. GREEN: `5099584`.
- RED checkpoint: `35a3650` (`test(gateway): expire scenarios during heartbeat`). An expired outage stayed active while telemetry was paused. GREEN: `692187b`.
- RED checkpoint: `fafafac` (`test(gateway): define dynamic plant control contracts`). Fifteen tests failed because computer-clock metadata, time-slotted variation, load/battery configuration, and the expanded scenarios did not exist. GREEN: `4dae143`.
- RED checkpoint: `2abc852` (`test(gateway): protect unsaved console controls`). The browser regression showed the 3-second refresh could replace one range value while the operator edited another. GREEN: `5cbe728`.
- RED checkpoint (2026-08-16 repair): three focused regressions failed before the fix. Reset discarded the delivery sequence and pending batches, reset left `latest` empty, console assets were cacheable across incompatible versions, and DOM synchronization assumed every control existed. GREEN: plant reset now preserves delivery state and ticks immediately; console assets use `Cache-Control: no-store`; rendering and startup event bindings safely ignore absent controls; dirty controls remain untouched until save; save handlers clear dirty state before refreshing.
- RED checkpoint (2026-08-21 verification replay): four focused tests failed because heartbeats did not carry cadence, publishing changes did not synchronize it, no completed-hour replay method existed, and the console endpoint returned 404. GREEN: 28 focused API/publisher tests passed; no commits were created because the user owns Git checkpoints and pushes.
- RED checkpoint (2026-08-25 graph-quality repair): the new continuity regression observed a 3.29 kW household jump between adjacent 30-second samples because every value was an independent uniform draw. GREEN: seeded anchor interpolation limits adjacent changes while preserving configured ranges, scenario effects, deterministic replay, and exact power balance.

## Test specification

| Guarantee | Test file | Type | Result |
|---|---|---|---|
| Rain reduces PV and inverter rating clips AC output | `tests/test_engine.py` | Unit | PASS |
| Adding an array increases available generation | `tests/test_engine.py` | Unit | PASS |
| Communications and operation are independent | `tests/test_engine.py` | Unit | PASS |
| Offline communications retain last telemetry time | `tests/test_engine.py` | Unit | PASS |
| Every snapshot obeys Aelora's power sign convention | `tests/test_engine.py` | Unit | PASS |
| System-clock mode uses the host-local hour and preserves the real UTC observation time | `tests/test_engine.py` | Unit | PASS |
| Load, clouds, and grid flow change across seeded 30-second intervals | `tests/test_engine.py` | Unit | PASS |
| The same seed and interval reproduce the same simulated values | `tests/test_engine.py` | Unit | PASS |
| Adjacent cloud and household readings follow bounded continuous changes rather than independent jumps | `tests/test_engine.py` | Unit | PASS |
| Local API adds arrays and changes weather | `tests/test_api.py` | Integration | PASS |
| Local API controls communications without stopping physical generation | `tests/test_api.py` | Integration | PASS |
| Publishing can be paused and interval changed | `tests/test_api.py` | Integration | PASS |
| Rotated credentials are stored without being echoed | `tests/test_api.py` | Integration | PASS |
| Exact outbound requests redact bearer credentials | `tests/test_api.py` | Integration | PASS |
| Timed scenarios start, stop, and restore state | `tests/test_api.py` | Integration | PASS |
| Household min/max controls validate and persist a dynamic demand range | `tests/test_api.py` | Integration | PASS |
| Battery capacity, SoC, reserve, target, and charge/discharge limits validate and persist | `tests/test_api.py` | Integration | PASS |
| Expanded cloud/load/inverter/battery/grid/night scenarios apply their intended plant change | `tests/test_api.py` | Integration | PASS |
| Live refreshes preserve unsaved settings until the operator saves them | `tests/test_api.py` plus browser regression | Contract/E2E | PASS |
| Console refresh cannot write through a missing DOM control | `tests/test_api.py` | Static contract | PASS |
| Console HTML and JavaScript cannot be reused across incompatible versions | `tests/test_api.py` | Integration | PASS |
| Plant reset preserves identity, sequence, and pending telemetry and emits a fresh tick | `tests/test_api.py` | Regression | PASS |
| Enrollment stores the returned gateway identity and credential locally | `tests/test_publisher.py` | Unit/integration | PASS |
| Failed batches persist and replay with bearer authentication | `tests/test_publisher.py` | Unit/integration | PASS |
| Heartbeats continue while telemetry publishing is paused | `tests/test_publisher.py` | Unit/integration | PASS |
| Heartbeats restore expired scenarios while telemetry is paused | `tests/test_publisher.py` | Regression | PASS |
| Heartbeats carry the current publish interval and publishing changes synchronize it immediately | `tests/test_publisher.py`, `tests/test_api.py` | Contract/integration | PASS |
| Completed-hour replay sends every cadence slot through bearer-authenticated ingestion without mutating live state | `tests/test_publisher.py` | Integration | PASS |
| The console exposes and wires the explicitly simulated development replay | `tests/test_api.py` | API/static contract | PASS |
| Fronius and SunSpec fixtures normalize to the same units/signs | `tests/test_adapters.py` | Contract | PASS |
| SunSpec scale factors are applied before normalization | `tests/test_adapters.py` | Unit | PASS |

## Final gates

- `python -m ruff check src tests` → PASS.
- `python -m pytest --cov=aelora_virtual_gateway --cov-report=term-missing --cov-fail-under=80` → 38 passed; 91.34% total coverage.
- `python -m compileall -q src tests` → PASS.
- `node --check src/aelora_virtual_gateway/static/app.js` → PASS.
- `pip-audit --skip-editable` → PASS: no known vulnerabilities; the editable local project is correctly excluded from the public-package lookup.
- Local smoke test on `http://127.0.0.1:4100/api/state` → PASS: computer and gateway local clocks matched to the second.
- Live interval regression → PASS: household load, PV, and grid flow all changed across an adjacent 30-second boundary while balance error remained `0.00 W`.
- End-to-end Aelora enrollment, heartbeat, credential rotation/promotion, persisted batch, timed grid-outage scenario, restoration, and dynamic telemetry HTTP `201` acceptance → PASS.
- Reset recovery → PASS: 11 already-buffered batches were backed up, resequenced above Aelora's persisted high-water mark, replayed in order, and accepted; a subsequent fresh batch returned HTTP `201` with an empty retry queue.
- Live API repair regression → PASS: adding an array, running one tick, publishing telemetry, and removing the test array completed with live metrics, populated plant devices, HTTP `201` delivery, and an empty retry queue. Full browser-driver replay was blocked by the local Chrome Playwright extension not being installed.
- Aelora gateway contract suite → PASS: 7/7 ingestion, heartbeat, replay-window, power-balance, and connectivity-freshness tests passed.
- Completed-hour integration proof → PASS: `2026-08-21T07:00:00Z` received 120/120 simulated 30-second readings; a repeat replay also returned 120/120 with zero buffered batches and an empty retry queue.

One non-failing warning comes from FastAPI's current `TestClient` compatibility layer suggesting a future Starlette transport dependency. It does not affect runtime behavior.
