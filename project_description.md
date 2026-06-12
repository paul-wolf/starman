# Starlink Management Console — v1 Build Spec

A self-hosted web console for monitoring and controlling a Starlink dish over its
local gRPC API, with an independent GPS-jamming watchdog. Built ground-up; the
`ertong/star-debug` repo is used only as a reference for which gRPC calls map to
which features.

## Goals

- Live + historical telemetry for one dish (the dish itself keeps almost no history).
- An **independent** GPS-jamming watchdog that inhibits/re-enables GPS automatically.
- On-demand controls (reboot, stow/unstow, manual GPS inhibit) behind auth.
- Run entirely on a Raspberry Pi, lightweight.

## Stack

| Layer | Choice | Notes |
|---|---|---|
| Web framework | Django | models, admin, migrations, settings |
| API | django-ninja | typed endpoints, Pydantic schemas, auto OpenAPI |
| DB | SQLite (WAL mode) | plenty for one dish; shared by web + watchdog |
| Poller/watchdog | Django **management command** | own process; only thing that polls the dish on a loop |
| Frontend | React + Vite | built to static assets, served by Django/whitenoise |
| Server (v1) | gunicorn (WSGI) | sync endpoints; no async needed in v1 |
| Live push (v2 only) | Channels + Daphne + Redis | deferred; see "v2 delta" |

## Core architectural rule

**Exactly one process polls the dish on a loop: the watchdog management command.**
The web app never polls the dish in a request. The web app reads the shared SQLite
DB for telemetry, and issues *on-demand* control calls directly via a shared gRPC
client module. This keeps GPS management alive even when nobody is viewing the
console, and avoids two pollers racing over the dish.

```
                 ┌────────────────────┐         writes (every poll)
   dish gRPC <───│  run_watchdog (cmd) │──────────────┐
   192.168.100.1 │  - poll get_status  │              ▼
        ▲        │  - debounce logic   │        ┌───────────┐
        │        │  - auto inhibit/clr │        │  SQLite   │
        │        └────────────────────┘        │  (WAL)    │
        │                                       └───────────┘
        │  on-demand control calls                    ▲
        │  (reboot/stow/inhibit-now)                  │ reads + rare writes
        └──────────────┌────────────────────┐─────────┘
                       │  Django + ninja API │
                       │  (gunicorn, WSGI)   │
                       └────────────────────┘
                                 ▲
                                 │ HTTP (poll every 2-3s in v1)
                       ┌────────────────────┐
                       │  React/Vite SPA     │
                       └────────────────────┘
```

## Project layout

```
console/                  # Django project
  settings.py
  urls.py                 # mounts ninja api + serves SPA
dish/                     # single app
  models.py
  schemas.py              # ninja/Pydantic schemas
  grpc_client.py          # the ONLY module that talks to the dish
  api.py                  # ninja router (read + control endpoints)
  watchdog.py             # pure logic (testable, no Django/IO coupling)
  management/commands/
    run_watchdog.py       # long-lived process: poll -> persist -> act
  protos/                 # vendored spacex.api.device protobufs (see gRPC client)
frontend/                 # vite + react; build output served by Django
manage.py
```

## gRPC client (`dish/grpc_client.py`)

Single chokepoint for all dish access, used by both the watchdog and the API.

- Use a real Python gRPC client, not `grpcurl` subprocess, for production.
  Vendor the compiled protobufs from `sparky8512/starlink-grpc-tools`
  (the `spacex.api.device` package) into `dish/protos/`. Concretely: copy
  the `spacex/` directory from that repo (it contains `__init__.py` plus
  `*_pb2.py` / `*_pb2_grpc.py` generated files) into `dish/protos/spacex/`,
  add an `__init__.py` at `dish/protos/__init__.py`, and import as
  `from dish.protos.spacex.api.device import device_pb2, device_pb2_grpc`.
  Alternatively, if the vendored files are stale or missing, regenerate with
  `python -m grpc_tools.protoc` against the `.proto` sources or via gRPC
  server reflection (`grpcurl … describe`). Channel target:
  `192.168.100.1:9200`, plaintext.
- Expose a thin, typed surface:
  - `get_status() -> StatusDict | None`
  - `get_config() -> ConfigDict | None`
  - `inhibit_gps(enabled: bool) -> bool`
  - `reboot() -> bool`
  - `stow(stow: bool) -> bool`
- **Graceful degradation is mandatory.** Catch `grpc.RpcError`; treat
  `UNIMPLEMENTED` as "feature absent on this firmware" and return a sentinel
  rather than raising. SpaceX changes this API without notice (e.g. the
  location endpoint was restricted in mid-2026 while `dish_inhibit_gps`
  survived). Never hard-depend on a single field.
- Parsing: pull known fields defensively (`.get(...)` with defaults). Booleans
  the dish considers "default" are **omitted** from the response — absent
  `gpsValid` means false; absent `inhibitGps` means not inhibited.

## Data model (`dish/models.py`)

### TelemetryReading  (one row per poll; the time series)
| field | type | source field |
|---|---|---|
| timestamp | DateTimeField(db_index=True, default=now) | — |
| gps_valid | BooleanField | gpsStats.gpsValid |
| gps_sats | IntegerField | gpsStats.gpsSats |
| gps_inhibited | BooleanField | gpsStats.inhibitGps |
| pnt_filter_state | CharField | gpsStats.pntFilterConvergenceState |
| pop_ping_latency_ms | FloatField(null=True) | popPingLatencyMs (-1 → null) |
| pop_ping_drop_rate | FloatField(default=0) | popPingDropRate |
| downlink_bps | FloatField(null=True) | downlinkThroughputBps |
| uplink_bps | FloatField(null=True) | uplinkThroughputBps |
| fraction_obstructed | FloatField(null=True) | obstructionStats.fractionObstructed |
| attitude_uncertainty_deg | FloatField(null=True) | alignmentStats.attitudeUncertaintyDeg |
| attitude_state | CharField | alignmentStats.attitudeEstimationState |
| uptime_s | BigIntegerField | deviceState.uptimeS |
| software_version | CharField | deviceInfo.softwareVersion |
| country_code | CharField | deviceInfo.countryCode |
| disablement_code | CharField | disablementCode |
| outage_cause | CharField(null=True) | outage.cause |
| mobility_class | CharField | mobilityClass |
| raw_json | JSONField | full get_status payload (forensics / future fields) |

Keep `raw_json` so schema drift never loses data and you can backfill new
columns later. Add a retention/downsampling job (management command) so the
table doesn't grow unbounded on the Pi — e.g. keep raw rows 7 days, then
1-per-minute, then 1-per-hour.

### Event  (discrete transitions and actions; the interesting log)
| field | type |
|---|---|
| timestamp | DateTimeField(db_index=True) |
| event_type | CharField (enum below) |
| source | CharField: WATCHDOG \| USER \| SYSTEM |
| actor | CharField(null=True)  # username for USER actions |
| detail | JSONField  # context: sats, elapsed, response, etc. |

`event_type` values: `GPS_DENIED`, `GPS_RECOVERED`, `INHIBIT_SET`,
`INHIBIT_CLEARED`, `OUTAGE_START`, `OUTAGE_END`, `REBOOT_DETECTED`,
`DISH_UNREACHABLE`, `CONTROL_ACTION`, `WATCHDOG_MODE_CHANGED`.

This unified log is what powers the "jamming episodes" timeline and the audit
trail. User-issued controls are Events with `source=USER` and the username in
`actor`.

### WatchdogConfig  (singleton; runtime settings + override state)
| field | type | default |
|---|---|---|
| mode | CharField: LOG_ONLY \| MONITOR \| ENFORCE | LOG_ONLY |
| poll_interval_s | IntegerField | 10 |
| deny_debounce_s | IntegerField | 90 |
| recover_debounce_s | IntegerField | 120 |
| min_sats_for_good | IntegerField | 5 |
| boot_warmup_s | IntegerField | 300 |
| manual_override_until | DateTimeField(null=True) | null |
| last_poll_at | DateTimeField(null=True) | null |
| updated_at | DateTimeField(auto_now=True) | — |

## Watchdog logic (`dish/watchdog.py` + `run_watchdog.py`)

Port the existing watchdog script into this app. Keep the **decision logic** in
`watchdog.py` as a pure function over (reading, config, prior-state) → action,
so it's unit-testable; the management command does the IO loop, persistence,
and gRPC calls.

Rules (carry over from the standalone script):
- `gps_good` = `gps_valid AND gps_sats >= min_sats_for_good`.
- **Boot warmup:** if `uptime_s < boot_warmup_s`, take no action and reset
  debounce timers. (The dish lacks a fix mid-reboot by design; inhibiting then
  is counterproductive — observed in testing.)
- **Inhibit** only after GPS denied continuously ≥ `deny_debounce_s`, and only
  in `ENFORCE` mode.
- **Clear** only after GPS good continuously ≥ `recover_debounce_s`.
- **Reboot detection:** track `uptime_s`; if it drops, log `REBOOT_DETECTED`
  and reset timers.
- Every poll: write a `TelemetryReading`, update `last_poll_at`. Log `Event`
  rows only on transitions, not every poll.
- **Dish unreachable (`get_status()` returns `None`):** skip writing a
  `TelemetryReading` for that poll, reset debounce timers (same as boot
  warmup — don't auto-inhibit while blind), and log a `DISH_UNREACHABLE`
  event only on the *transition* to unreachable (not every poll). When
  connectivity returns, log the recovery and resume normal logic. Apply a
  back-off (e.g. 3× the normal `poll_interval_s`) after repeated failures
  so the Pi doesn't hammer a dead gRPC connection.

Modes:
- `LOG_ONLY` — record what it *would* do; never calls `inhibit_gps`. Run here
  first for a few days to learn the real jamming pattern before enforcing.
- `MONITOR` — same as LOG_ONLY for now (reserved for "alert but don't act").
- `ENFORCE` — actually toggles the flag.

**Manual override precedence (who wins the inhibit flag):**
When a user sets inhibit via the API, the API writes the flag AND sets
`manual_override_until = now + grace` (e.g. 30 min). The watchdog must **not**
auto-toggle while `now < manual_override_until`, except it may still inhibit on
genuine sustained denial (safety beats the hold). After the hold expires, the
watchdog resumes normal automatic management. This prevents the watchdog and a
human from fighting over the flag.

## API (`dish/api.py`, django-ninja)

Auth: use Django's auth with ninja's `django_auth` (session-based, since the SPA
is served same-origin). **All** endpoints require auth — it's on a shared LAN.
Control endpoints additionally log a `CONTROL_ACTION` event with the actor.

### Read
- `GET /api/status/live` → latest TelemetryReading (frontend polls this ~2-3s).
- `GET /api/status/history?since&until&fields` → downsampled series for charts.
- `GET /api/events?since&type&limit` → event log / episode timeline.
- `GET /api/gps/state` → `{ valid, sats, inhibited, watchdog_mode, manual_hold_until }`.
- `GET /api/dish/info` → device info (hw/sw version, id, country) — slow-changing.
- `GET /api/watchdog/config` → current WatchdogConfig.

### Control (auth + audit)
- `POST /api/control/inhibit-gps` body `{ enabled: bool }` → sets flag, sets
  manual hold, logs event. Returns new state.
- `POST /api/control/reboot` → **requires explicit confirm** (e.g. body
  `{ confirm: true }`); logs event.
- `POST /api/control/stow` body `{ stow: bool }`.
- `POST /api/watchdog/config` body `{ mode?, deny_debounce_s?, recover_debounce_s?,
  min_sats_for_good? }` → updates singleton; logs `WATCHDOG_MODE_CHANGED` on mode change.

Schemas (`schemas.py`) are plain Pydantic/ninja models mirroring the above. Use
ninja's ability to build response schemas from the ORM for the read endpoints.

## SQLite sharing contract

- Enable WAL: set `PRAGMA journal_mode=WAL;` (Django: via a connection init, or a
  one-time migration/management step) so the watchdog (writer) and Django
  (reader + rare writer) don't block each other. Set `PRAGMA busy_timeout=5000`.
- Both processes use the **same Django ORM and settings** (the watchdog is a
  management command), so there's one DB config, migrations apply once, models
  are shared.
- Write ownership: watchdog writes `TelemetryReading` (every poll) and most
  `Event` rows; the API writes `Event` rows for user controls and updates
  `WatchdogConfig`. Telemetry writes are tiny and infrequent (1 per 10s), so
  contention is negligible; `busy_timeout` covers the rare overlap.

## Frontend (React + Vite)

- **Dashboard tiles:** GPS (valid / sats / inhibited), latency, drop rate,
  down/up throughput, obstruction %, attitude state + uncertainty, uptime,
  software version, country, disablement code.
- **Charts** (recharts or similar): gps_sats, latency, drop rate, obstruction
  over selectable windows. Pull from `/api/status/history`.
- **Episode timeline:** render `/api/events` — jamming episodes, inhibit
  transitions, outages, reboots.
- **Controls panel:** GPS inhibit toggle; reboot (confirm modal); stow/unstow;
  watchdog mode selector + threshold tuning form.
- **Live update (v1):** `setInterval` hitting `/api/status/live` every 2-3s and
  `/api/gps/state`; history/events on a slower cadence or on demand. This is
  indistinguishable from "live" for one dish and needs no WebSockets.
- **Build/serve:** `vite build` → static bundle served by Django (whitenoise) or
  nginx. No Node at runtime on the Pi. Dev: vite dev server proxying `/api` to
  Django.

## Deployment on the Pi

- Two systemd services, same user, both pointing at the same DB file:
  1. `gunicorn console.wsgi` (the web app).
  2. `python manage.py run_watchdog` (the poller/watchdog) — `Restart=always`.
- The watchdog runs regardless of the web app's state (GPS management is
  safety-of-service, not a UI feature).
- **Dish reachability:** the Pi must have a route to `192.168.100.1` — verify
  this *before* first run with `ping 192.168.100.1` from the Pi. Two options:
  (a) add a static route on the Pi pointing `192.168.100.0/24` at the router
  that already reaches the dish (the same way the Mac reaches it) — do this
  with `ip route add 192.168.100.0/24 via <router-IP>` and persist it via
  `/etc/network/interfaces` or a systemd-networkd `.network` file; or
  (b) give the Pi a second network interface with an address on the
  `192.168.100.x` subnet (e.g. a USB-Ethernet adapter plugged into the dish's
  LAN port). Option (a) is simpler if the router already forwards the subnet;
  option (b) is more reliable and removes the router as a dependency.
  This is a hard prerequisite — the watchdog and gRPC client will fail
  immediately without it.
- Static asset serving via whitenoise keeps it to a single process; add nginx
  only if you want TLS or to front multiple services.

## v2 delta — live push (only when you actually want it)

Everything above is unchanged; you add push when 2-3s polling isn't enough or you
have multiple viewers.

- Switch the web server to ASGI: Daphne (or uvicorn) instead of gunicorn.
- Add `channels` + `channels-redis` + a Redis instance on the Pi.
- After writing each `TelemetryReading`, the **standalone watchdog** publishes to
  a channel-layer group (`group_send`). Because the watchdog and the web process
  are **separate processes**, the broadcast must cross a process boundary — this
  is precisely why Redis (the cross-process channel layer) is needed here, and
  the one scenario where it earns its place. (`InMemoryChannelLayer` would only
  work if polling lived inside the web process, which we deliberately avoid.)
- A Channels `AsyncWebsocketConsumer` joins the group and forwards updates to
  browsers.
- Frontend swaps the `setInterval` poll for a WebSocket subscription; tiles and
  charts update on push.
- Control endpoints can become async ninja endpoints issuing gRPC directly; the
  continuous loop still lives only in the watchdog.

## Suggested build order for Claude Code

1. Django project + `dish` app + models + admin + WAL setup + migrations.
2. `grpc_client.py` with graceful degradation; a `manage.py poll_once` smoke test
   that prints parsed status.
3. `watchdog.py` pure logic + unit tests; then `run_watchdog` command (start in
   LOG_ONLY).
4. ninja read endpoints + a minimal React dashboard polling `/api/status/live`.
5. Auth + control endpoints + audit events + confirm flows.
6. Charts, episode timeline, watchdog config UI.
7. systemd units + retention/downsampling command.
8. (Later) v2 push.

## References to point Claude Code at

- `sparky8512/starlink-grpc-tools` — working Python gRPC client + compiled
  `spacex.api.device` protobufs to vendor; authoritative call/field shapes.
- `ertong/star-debug` (Dart) — read the request-builder code to confirm which
  gRPC messages back which features (reboot/stow/GPS on-off/wifi).
- The dish's own reflection: `grpcurl -plaintext 192.168.100.1:9200 describe
  SpaceX.API.Device.Request` is the ground truth for what *your* firmware exposes.
