# Celery Migration Plan: Replace dispy with Celery for Distributed Computing

**Historical proposal, February 2026.** For the implemented configuration, see
[scientific workers](docs/installation/cli-tools.md#scientific-workers).
The implementation uses JSON messages and PostgreSQL execution receipts.
The pickle transport, remote software distribution, and cloud provisioning
described below were proposals.

## Context

GeoDE uses **dispy** for distributed GNSS processing across compute nodes. dispy is
effectively unmaintained (last release 2021-2022), uses fragile UDP broadcast for
node discovery, and doesn't work well with cloud infrastructure. The web backend
already runs Celery + Redis (inside a single Docker container) for one background
task. This plan migrates all distributed computing to Celery, extracts Redis as a
standalone service, and prepares the architecture for cloud spot-instance workers.

**User decisions:**
- Keep local execution mode (`parallel=False`) — no broker required
- Celery app lives in `geode/distributed/` as an optional dependency
- Broker URL: env var `CELERY_BROKER_URL` with `gnss_data.cfg [celery]` fallback

---

## Phase 1: Extract Redis from Backend Container

**Goal:** Redis becomes a standalone Docker service reachable by both the web
backend and future compute workers.

### Files to modify

**`docker-compose.yml`** — Add `redis` service before `backend`:
```yaml
services:
  redis:
    image: redis:7-alpine
    container_name: gnss-redis
    command: redis-server --save "" --appendonly no
    ports:
      - "${REDIS_PORT:-6379}:6379"
    restart: always
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 3

  backend:
    # ... existing config ...
    depends_on:
      redis:
        condition: service_healthy
    environment:
      # ... existing vars ...
      - REDIS_URL=${REDIS_URL:-redis://redis:6379/0}
```

**`web/backend/Dockerfile`** (line 11) — Remove `redis-server` from apt-get install.

**`web/backend/supervisord.conf`** (lines 27-30) — Remove entire `[program:redis]` block.

**`web/backend/.../settings.py`** (lines 25-36) — Parameterize Redis URLs:
```python
_redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
CELERY_BROKER_URL = _redis_url
CELERY_RESULT_BACKEND = _redis_url
CACHES = {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache",
                       "LOCATION": _redis_url}}
```

**`.env.example`** — Add `REDIS_URL=redis://redis:6379/0` section.

### Verify
- `docker compose up redis` — responds to `redis-cli ping`
- `docker compose up` — backend connects, `update_gaps_status` task works

---

## Phase 2: Create `geode/distributed/` Package

**Goal:** Celery app and task definitions as optional dependencies of geode-gnss.

### New files to create

```
geode/distributed/
    __init__.py          # Package init, guarded import of get_celery_app
    celery_app.py        # Celery app factory + module-level app instance
    config.py            # Broker URL resolution (env var -> gnss_data.cfg -> default)
    health.py            # check_worker task (replaces test_node validation)
    worker.py            # geode-worker CLI entry point
    tasks/
        __init__.py      # Package docstring
        gamit.py         # run_gamit_session, run_globk, run_parse_ztd
        generic.py       # execute_function (fallback for unregistered functions)
```

### Key design: `celery_app.py`

```python
app = Celery("geode")
app.conf.update(
    broker_url=get_broker_url(),          # from config.py
    result_backend=get_result_backend(),
    task_serializer="pickle",             # MUST use pickle — GamitTask etc. are complex objects
    result_serializer="pickle",
    accept_content=["pickle", "json"],
    task_acks_late=True,                  # spot-instance safety: requeue on worker death
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,         # one GAMIT task per worker process
    result_expires=86400,
    task_routes={
        "geode.distributed.tasks.gamit.*":    {"queue": "gamit"},
        "geode.distributed.tasks.generic.*":  {"queue": "compute"},
        "geode.distributed.tasks.stacker.*":  {"queue": "compute"},
    },
)
```

Pickle serializer is required because existing code passes complex objects
(`GamitTask`, `GlobkTask`, `ParseZtdTask`, `pyDate.Date`, nested config dicts)
as task arguments. JSON serialization would require rewriting every task function
and every call site — out of scope for this migration.

### Key design: `config.py`

Resolution order for broker URL:
1. `CELERY_BROKER_URL` env var
2. `REDIS_URL` env var (Docker compatibility)
3. `gnss_data.cfg` `[celery]` section `broker_url` key
4. Default: `redis://localhost:6379/0`

### Key design: `tasks/gamit.py`

Thin wrappers that call existing logic — no code duplication:
```python
@app.task(name="geode.distributed.tasks.gamit.run_gamit_session",
          bind=True, max_retries=1, queue="gamit")
def run_gamit_session(self, gamit_task_obj, dir_name, year, doy, dry_run):
    return gamit_task_obj.start(dir_name, year, doy, dry_run)
```

### Key design: `tasks/generic.py`

Fallback for functions that don't have explicit Celery tasks registered
(Stacker, DRA, KML, IntegrityCheck, etc.):
```python
@app.task(name="geode.distributed.tasks.generic.execute_function")
def execute_function(func, args):
    return func(*args)
```

This mirrors dispy's "ship any function" model and means CLI tools that pass
arbitrary functions to `create_cluster()` need zero changes.

### Key design: `health.py`

`check_worker` task replaces dispy's `test_node()`. Validates on a remote worker:
Python version, geode imports, DB connectivity, GAMIT executables, archive paths.
Returns `{"success": bool, "node": str, "errors": [str]}`.

### Key design: `worker.py`

Entry point for `geode-worker` CLI command:
```bash
geode-worker --queues gamit,compute --concurrency 4 --loglevel info
```
Wraps `celery -A geode.distributed.celery_app worker`.

### `pyproject.toml` changes

```toml
[project.optional-dependencies]
distributed = ["celery>=5.4,<6", "redis>=5.0,<6"]

[project.scripts]
geode-worker = "geode.distributed.worker:main"

[tool.setuptools.packages.find]
include = ["geode*"]
```

Remove `packages = ["geode"]` (line 69) — the `find` config auto-discovers
all subpackages including `geode.distributed`.

### `gnss_data.cfg.example` — Add `[celery]` section

```ini
[celery]
# Celery broker URL (can be overridden by CELERY_BROKER_URL env var)
broker_url = redis://localhost:6379/0
result_backend = redis://localhost:6379/0
```

### Verify
- `pip install -e ".[distributed]"` installs celery + redis
- `python -c "from geode.distributed import get_celery_app"` succeeds
- `celery -A geode.distributed.celery_app inspect ping` reaches workers

---

## Phase 3: Refactor `pyJobServer.py`

**Goal:** Replace dispy internals with Celery while preserving the exact same
public API. This is the critical phase — 8 CLI tools depend on this API.

### Public API to preserve (used by all CLI tools)

```python
JobServer.__init__(Config, check_gamit_tables=None, check_archive=True,
                   check_executables=True, check_atx=True, run_parallel=True,
                   software_sync=())
JobServer.create_cluster(function, deps=(), callback=None, progress_bar=None,
                         verbose=False, modules=(), on_nodes_changed=None,
                         node_setup=None, node_cleanup=None)
JobServer.submit(*args)
JobServer.submit_async(*args)         # used by DownloadSources only
JobServer.wait()
JobServer.close_cluster()
JobServer.progress_bar                # set externally by IntegrityCheck
JobServer.run_parallel                # read by DownloadSources
```

### Callback compatibility: `JobResult` class

All 8 CLI tools' callbacks access these properties on the dispy job object:
- `job.result` — return value
- `job.exception` — exception if failed
- `job.ip_addr` — worker hostname (used by ParallelGamit, Stacker, DRA)
- `job.id` — task ID (used by DownloadSources)

Create a `JobResult` shim class providing these same attributes.

### `WorkerNode` compatibility class

DownloadSources' `on_nodes_changed` callback expects nodes with `.avail_cpus`.
Create a lightweight `WorkerNode(name, avail_cpus)` class, populated from
Celery's `inspector.stats()`.

### Execution modes

**`run_parallel=False` (local mode):**
- No Celery/Redis imports needed (guarded behind `try/except ImportError`)
- `submit()` calls the function in-process, wraps result in `JobResult`
- `submit_async()` uses a thread (existing `_job_runner_thread` pattern)
- `test_node()` runs locally (existing behavior)

**`run_parallel=True` (distributed mode):**
- Requires `geode-gnss[distributed]` installed
- `__init__()` pings Celery workers via `inspector.ping()`, runs `check_worker`
  health task on each
- `create_cluster()` stores the function reference and callback
- `submit(*args)` maps function to a registered Celery task (if found) or uses
  `execute_function` generic task; stores `AsyncResult` + `JobResult` pair
- `wait()` polls `AsyncResult.ready()` in a loop, fires callbacks as results
  arrive, updates progress bar
- `close_cluster()` clears state

### Callback timing change

In dispy, callbacks fire immediately via the `cluster_status` event. In Celery,
callbacks fire during the `wait()` polling loop. This is safe because ALL 8 CLI
tools follow the same pattern: submit all jobs, then `wait()`, then process.
No CLI tool depends on callbacks firing *during* submission.

### File: `geode/pyJobServer.py` — Complete rewrite

Remove all `import dispy` / `import dispy.httpd` references. The file retains
`test_node()` and `setup()` functions (used for local mode), plus the rewritten
`JobServer` class.

### Verify
- Run each CLI tool with `--noparallel` — identical behavior
- Run ParallelGamit in parallel mode with a Celery worker — tasks execute,
  callbacks fire, results match
- `KeyboardInterrupt` during `wait()` revokes pending tasks

---

## Phase 4: Update CLI Tools (Minimal Changes)

**Goal:** Because Phase 3 preserves the JobServer API, most CLI tools need
zero or minimal changes.

### No changes needed (API-compatible via JobResult shim)
- `com/GenerateKml.py` — `job.result` only
- `com/IntegrityCheck.py` — `job.result`, `job.exception`
- `com/ArchiveService.py` — `job.result`, `job.exception`
- `com/ScanArchive.py` — `job.result`, `job.exception`
- `com/DRA.py` — `job.result`, `job.exception`, `job.ip_addr`
- `com/Stacker.py` — `job.result`, `job.exception`, `job.ip_addr`
- `com/ParallelGamit.py` — `job.result`, `job.exception`, `job.ip_addr`

### Minor changes needed
- `com/DownloadSources.py` — Uses `submit_async`, `on_nodes_changed`,
  `job.id`. All provided by `JobResult` and `WorkerNode` shims. Verify the
  `JobsManager` class works with the new node objects.

### Verify
- Run each CLI tool with `--noparallel` and confirm identical output
- Run DownloadSources and verify `on_nodes_changed` callback fires

---

## Phase 5: Update Django Backend

**Goal:** Point Django's existing Celery app at the external Redis (already done
in Phase 1). Add pickle acceptance for cross-app compatibility.

### Files to modify

**`web/backend/.../settings.py`** — Add pickle to accepted content:
```python
CELERY_ACCEPT_CONTENT = ['json', 'pickle']
```

The Django Celery app (`backend_django_project/celery.py`) stays separate from
`geode.distributed.celery_app`. Both point at the same Redis broker. The Django
app handles web tasks (`update_gaps_status` on `default` queue); geode's app
handles compute tasks (`gamit`, `compute` queues).

### Verify
- `docker compose up` — backend starts, connects to Redis service
- Trigger `update_gaps_status` via API — completes successfully

---

## Phase 6: Remove dispy Dependency

**Goal:** Clean removal after all phases are validated.

### `pyproject.toml` — Remove from `dependencies`:
```
"dispy",
"pycos",
```

Also remove `"netifaces>=0.10.9"` if only used by dispy (verify with grep first).

### `geode/pyJobServer.py` — Already cleaned in Phase 3, but verify:
```bash
grep -r "import dispy\|import pycos\|from dispy\|from pycos" geode/ com/
```
Should return zero matches.

### Verify
- `pip install -e .` — no dependency errors
- `python -c "import geode"` — clean import
- `pytest geode/tests/` — all tests pass

---

## Phase 7: Configuration & Documentation

**Goal:** Document worker setup for Packer golden images and queue architecture.

### Queue architecture
```
           Redis (broker)
          /      |       \
     [default] [gamit]  [compute]
        |         |         |
     Django    GAMIT      ETM, DRA
     backend   workers    KML, etc.
     (web)   (spot inst.) (spot inst.)
```

### Worker startup (baked into Packer image)
```bash
# systemd service or direct:
geode-worker --queues gamit,compute --concurrency 4 --loglevel info

# Environment required:
CELERY_BROKER_URL=redis://broker-host:6379/0
```

### Worker node requirements (for Packer image)
- `geode-gnss[distributed]` installed
- `gnss_data.cfg` with DB credentials and archive paths
- GAMIT/GLOBK at `~/gg/` with tables
- RINEX utilities in PATH
- PostgreSQL network access
- Shared filesystem access (archive, repository, production dirs)

### Files to create/update
- `gnss_data.cfg.example` — add `[celery]` section
- `.env.example` — already updated in Phase 1

---

## Implementation Order & Dependencies

```
Phase 1 (Extract Redis)  ──────────────> Phase 5 (Django backend)
    |
    v
Phase 2 (geode/distributed/ package)
    |
    v
Phase 3 (Refactor pyJobServer.py)
    |
    v
Phase 4 (Verify CLI tools)
    |
    v
Phase 6 (Remove dispy)
    |
    v
Phase 7 (Docs & config)
```

Phases 1 and 2 can be done in parallel. Phase 5 depends only on Phase 1.
Phase 6 is cleanup after 3+4 are validated.

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Pickle security | Workers accept only trusted broker connections. Redis requires auth in production. |
| Callback timing (polled vs immediate) | All CLI tools use submit-then-wait pattern. Polled callbacks are equivalent. |
| Spot instance preemption | `task_acks_late=True` + `task_reject_on_worker_lost=True` requeue lost tasks. |
| Complex objects fail to unpickle | Same Python + geode version on coordinator and workers (enforced by Packer image). |
| `visibility_timeout` for long tasks | Set to 2h+ for GAMIT tasks (default 1h can cause re-delivery). |

---

## Critical Files Summary

| File | Action | Phase |
|------|--------|-------|
| `docker-compose.yml` | Add redis service, update backend | 1 |
| `web/backend/Dockerfile` | Remove redis-server | 1 |
| `web/backend/supervisord.conf` | Remove [program:redis] | 1 |
| `web/backend/.../settings.py` | Parameterize Redis URLs | 1, 5 |
| `.env.example` | Add REDIS_URL | 1 |
| `geode/distributed/__init__.py` | New | 2 |
| `geode/distributed/celery_app.py` | New | 2 |
| `geode/distributed/config.py` | New | 2 |
| `geode/distributed/health.py` | New | 2 |
| `geode/distributed/worker.py` | New | 2 |
| `geode/distributed/tasks/__init__.py` | New | 2 |
| `geode/distributed/tasks/gamit.py` | New | 2 |
| `geode/distributed/tasks/generic.py` | New | 2 |
| `pyproject.toml` | Optional deps, entry point, packages.find | 2, 6 |
| `gnss_data.cfg.example` | Add [celery] section | 2 |
| `geode/pyJobServer.py` | Complete rewrite | 3 |
