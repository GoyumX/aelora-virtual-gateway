# Hosted demo gateway TDD evidence

## User journeys

1. A local operator starts the gateway without hosted-demo variables and uses
   the console exactly as before.
2. A presenter opens the public Railway URL, authenticates, changes simulated
   equipment, and Aelora receives the resulting telemetry.
3. An unauthenticated internet visitor cannot read state, enroll the gateway, or
   mutate equipment.
4. Railway can call the public health endpoint without presentation credentials.
5. A deployment with missing or weak console credentials fails before it can
   expose an unprotected console.
6. Railway's injected port overrides the localhost default.
7. A persistent Railway volume is made writable before the process drops to the
   unprivileged application user.

## RED evidence

`pytest tests/test_deployment_contract.py` failed during collection because
`resolve_port` did not exist. The container contract then failed because the
volume-aware `docker-entrypoint.sh` did not exist.

## GREEN evidence

The hosted deployment tests cover local compatibility, Basic Authentication,
public health, fail-fast credential validation, Railway port precedence, and
the privilege-dropping container entrypoint. The complete suite and coverage
commands are recorded in the final verification commit and CI run.
