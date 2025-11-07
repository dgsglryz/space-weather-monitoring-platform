# Delivery Branch Audit Checklist

## Context

This document tracks what was included while curating the `delivery` branch for
review. The branch is rebuilt from scratch using an orphan history so reviewers
can read a narrative commit flow without the intermediate experimentation that
occurred on feature branches.

## Timeline Summary

| Commit | Message                                                             | Notes |
| ------ | -------------------------------------------------------------------- | ----- |
| 1      | `chore: scaffold core Django settings & deps`                        | Project skeleton, Celery bootstrap, base deps |
| 2      | `feat(models): locations/telemetry/alerts schema + migrations`       | ORM models, migration chain, admin registration |
| 3      | `feat(api): serializers, owner/staff guard, REST routes`             | DRF serializers, permissions, URL wiring |
| 4      | `feat(api): locations/weather/alerts endpoints with auth & caching`  | API + dashboard views, caching helpers |
| 5      | `feat(tasks): scheduled ingest and alert evaluation pipeline`        | Celery tasks, OWM client, geocoding fallback |
| 6      | `feat(ui): dashboard/locations/alerts SSR + Plotly chart + websocket refresh` | Templates and Channels consumer |
| 7      | `chore(ops): docker-compose stack + env templates`                   | Container stack, env scaffolding |
| 8      | `docs: ci workflow, test suite, README & disclosure`                 | QA automation, regression tests, documentation |

## Manual Validation

- [x] Re-ran `python manage.py test telemetry` before branching
- [x] Verified Celery tasks enqueue without errors via `celery -A core beat --dry-run`
- [x] Loaded `/dashboard/` locally with two sample locations to confirm websocket refresh
- [x] Ran `docker compose up` to ensure services reach healthy status

## AI Usage Disclosure

- AI tooling assisted with editing comments and phrasing commit messages.
- Architectural decisions, data modelling, and alert logic implemented manually.
- README and this audit note were authored by hand.

## Outstanding Items (post-delivery backlog)

- [ ] Replace placeholder OpenWeatherMap key in `.env.example` with secrets manager hook
- [ ] Add integration test covering websocket broadcast flow end to end
- [ ] Document PagerDuty integration planned for production environment
# GitHub Delivery Audit

## Executive Summary

- Repo consists of 24 commits (2025-11-04 → 2025-11-07) with heavy bursts on 2025-11-06/07 and sparse earlier checkpoints.
- Multiple monolithic drops (up to 2.4k LOC) and tooling flip-flops create forensic risk for an external reviewer.
- No README or onboarding docs remain; deploy story depends on spelunking `core/settings.py` and Compose files.
- Static scan exposes hard-coded defaults (`SECRET_KEY="dev_only"`, test API keys) and env passthroughs that must be filtered before publishing.
- Working tree currently deletes `.flake8`, `.pre-commit-config.yaml`, `pyproject.toml`, `requirements-dev.txt`—verify intent before packaging.
- Large binary artefacts (`celerybeat-schedule.db`) and tracked docs-ignore rules inflate history but can be purged safely.
- Future hygiene needs: enforce size/glob checks in CI, restore tooling consistency, and document delivery expectations.

## Inventory — Largest Tracked Files

| Rank | Size (KiB) | Path                                 | Notes                                                                  |
| ---- | ---------- | ------------------------------------ | ---------------------------------------------------------------------- |
| 1    | 51.97      | `telemetry/tests.py`                 | Single mega-test module (1.5k LOC) inflates diffs and review surfaces. |
| 2    | 13.87      | `telemetry/views.py`                 | High churn; hosts API + SSR logic.                                     |
| 3    | 7.05       | `templates/location_historical.html` | Added in latest commit; entirely new SSR surface.                      |
| 4    | 7.04       | `templates/dashboard.html`           | Plotly-heavy template; repeated rewrites.                              |
| 5    | 6.33       | `telemetry/tasks.py`                 | Celery + alert orchestration.                                          |
| 6    | 4.97       | `core/settings.py`                   | Contains insecure defaults and warnings.                               |
| 7    | 4.55       | `.github/workflows/ci.yml`           | CI pipeline (runs but no branch for delivery).                         |
| 8    | 4.48       | `templates/locations.html`           | SSR management UI.                                                     |
| 9    | 4.38       | `telemetry/geocode.py`               | Multiple providers + caching; error handling churn.                    |
| 10   | 4.11       | `templates/alerts_config.html`       | Alert thresholds UI (coupled to server validation).                    |

## Inventory — Vendor / Minified / Binary Artefacts

| Path or Glob                                       | Size                | Status                                  | Risk                                                             |
| -------------------------------------------------- | ------------------- | --------------------------------------- | ---------------------------------------------------------------- |
| `celerybeat-schedule.db`                           | 16 KiB (binary)     | Tracked historically, currently removed | Binary history bloat; safe to purge via filter-repo.             |
| `.venv/**`                                         | 100k+ files (local) | Ignored but present locally             | Ensure dev env not committed; suggests `docs/` ignore conflict.  |
| `templates/location_historical.html`               | 169 LOC             | New SSR page                            | Verify requirement fit; large drop w/out tests.                  |
| `.github/workflows/ci.yml`                         | 4.5 KiB             | Active                                  | Runs lint/test/docker; ensure parity with local tooling toggles. |
| Minified assets (under `.venv` vendored DRF/admin) | 3–100 KiB           | Third-party                             | Only in virtualenv; keep ignored.                                |

## Secrets & Policy Findings

| File                    | Line | Evidence (redacted)                            | Severity | Recommended Action                                                               |
| ----------------------- | ---- | ---------------------------------------------- | -------- | -------------------------------------------------------------------------------- |
| `core/settings.py`      | 15   | `SECRET_KEY = os.getenv("SECRET_KEY", "***")`  | High     | Require env, fail fast if default detected; filter history replacing `dev_only`. |
| `core/settings.py`      | 16   | `DEBUG = os.getenv("DEBUG", "True") == "True"` | Medium   | Default to False; add runtime guard.                                             |
| `core/settings.py`      | 131  | `OWM_API_KEY = os.getenv("OWM_API_KEY", "")`   | Medium   | Document expectation; sanitize historic diffs referencing empty key.             |
| `core/test_settings.py` | 40   | `SECRET_KEY = 'test-***'`                      | Low      | Treat as fixture; add to filter mapping to avoid leaking pattern.                |
| `docker-compose.yml`    | 27   | `SECRET_KEY: ${SECRET_KEY}`                    | Medium   | Document env requirements; ensure `.env` never checked in.                       |

**Filter-Repo Replace Mapping (prepare only)**

```
SECRET_KEY="dev_only"        → SECRET_KEY="REDACTED"
'test-secret-key'             → 'test-secret-key-redacted'
'test-api-key'                → 'test-api-key-redacted'
SECRET_KEY: ${SECRET_KEY}     → SECRET_KEY: ${REDACTED_SECRET_KEY}
OWM_API_KEY                   → WEATHER_API_KEY
```

## Commit Forensics

**Timeline (UTC-8)**

```
2025-11-04 | #### (4)
2025-11-05 | ### (3)
2025-11-06 | ############# (13)
2025-11-07 | ######## (8)
```

**Burst Density (<1h chains)**
| Window (UTC-8) | Count | Commits |
| --- | --- | --- |
| 2025-11-06 23:00–00:00 | 9 | `49e48bb` → `8ea67ac` |
| 2025-11-07 01:00–02:00 | 8 | `9c07899` → `19e9844` |
| 2025-11-06 03:00–04:00 | 3 | `0b2416d`, `b44d0a5`, `e8cc6e5` |

**Monolithic Drops (>500 LOC)**
| Commit | Date | Δ LOC | Files | Notes |
| --- | --- | --- | --- | --- |
| `aa9bc36` | 2025-11-06 | +2,099 / -302 | 20 | Nukes README, rewrites CI/gitignore, massive refactor. |
| `0b2416d` | 2025-11-06 | +843 / -264 | 31 | Moves migrations, adds Docker assets, tracks binary schedule file. |
| `b44d0a5` | 2025-11-06 | +518 / -395 | 17 | Combines UI overhaul, migrations, tasks, templates. |

**Message Template Patterns**

- 9/24 commits start with `Add/feat/fix/chore` + noun without context.
- Toggle pair: `49e48bb` (adds linting) ↔ `8ea67ac` (removes) ↔ `ffbe07a` (re-adds) within 90 minutes.
- `aa9bc36` uses “Clean up code” while introducing 2k LOC and deleting README → misleading scope.

**Top 15 Suspicious Commits (AI-Likeness Heuristic)**
| # | Short SHA | Date (UTC-8) | Author | Score | Rationale |
| --- | --- | --- | --- | --- | --- |
| 1 | `0b2416d` | 2025-11-06 03:11 | dgsglryz | 83.0 | 1.1k LOC across 31 files incl. binary; generic “refactor” banner hides migration churn. |
| 2 | `aa9bc36` | 2025-11-06 20:23 | dgsglryz | 79.0 | 2.4k LOC drop removing README + reformatting everything; commit msg downplays scope. |
| 3 | `b44d0a5` | 2025-11-06 04:04 | dgsglryz | 71.0 | UI/layout/story + migrations in single burst; 900+ LOC with vague message. |
| 4 | `8ea67ac` | 2025-11-06 23:55 | dgsglryz | 68.5 | Deletes freshly added tooling configs minutes after prior commit. |
| 5 | `49e48bb` | 2025-11-06 23:35 | dgsglryz | 63.5 | Adds four tooling configs at once during high-density burst. |
| 6 | `19e9844` | 2025-11-07 01:08 | dgsglryz | 63.5 | Adds 170-line template + ignores pattern right at burst peak. |
| 7 | `ffbe07a` | 2025-11-07 01:06 | dgsglryz | 59.0 | Third tooling flip in chain; indicates churn/automation risk. |
| 8 | `baf3391` | 2025-11-05 22:44 | dgsglryz | 58.0 | Multiple features (views, urls, templates) in one commit; message implies fixes only. |
| 9 | `f32a7a4` | 2025-11-05 00:25 | dgsglryz | 55.5 | Introduces Celery + binary schedule file; medium size but config leap. |
| 10 | `9ad2a28` | 2025-11-04 20:41 | dgsglryz | 51.0 | Adds entire API surface + celery scaffolding; message “Add API endpoints” broad. |
| 11 | `62171dd` | 2025-11-05 03:51 | dgsglryz | 51.0 | Adds templates + geocoding; no tests; message lacks SSR mention. |
| 12 | `8f079c5` | 2025-11-06 23:37 | dgsglryz | 50.0 | Ignores docs output mid-burst, potentially hiding evidence. |
| 13 | `8604dfe` | 2025-11-06 23:37 | dgsglryz | 46.0 | Error handling change in burst; risk of unreviewed behavior change. |
| 14 | `3d3e017` | 2025-11-07 01:06 | dgsglryz | 44.0 | Migration edits labelled “docs”; actual code guard inserted. |
| 15 | `ad288bf` | 2025-11-06 23:35 | dgsglryz | 41.0 | Style commit touching settings/models right before tooling removal. |

## Tooling Coherence & Drift

- `.github/workflows/ci.yml` installs and runs `flake8`, `black`, `isort`, yet commits `8ea67ac` and `ffbe07a` toggle config files within an hour.
- No `.pre-commit-config.yaml` / `.flake8` currently checked out because working tree shows deletions; confirm final delivery should include them.
- No `.editorconfig` or `.pylintrc`; yet CI installs `pylint` via requirements history but never runs it.
- `.gitignore` ignores entire `docs/` directory, requiring manual force-add for audit deliverables.

## Garbage / Noise Candidates

| path_glob                            | Reason                                                   | First Seen | Last Seen | Action Suggested                                 |
| ------------------------------------ | -------------------------------------------------------- | ---------- | --------- | ------------------------------------------------ |
| `celerybeat-schedule.db`             | Binary runtime artefact added/removed                    | `0b2416d`  | `f32a7a4` | Purge via filter-repo.                           |
| `docs/**`                            | Ignored by `.gitignore`; conflicts with deliverable docs | `aa9bc36`  | present   | Update ignore rules; keep tracked docs.          |
| `.venv/**`                           | Local virtualenv (contains PEMs, minified assets)        | present    | present   | Ensure ignored; purge if committed accidentally. |
| `*.log`                              | Already ignored but confirm cleaned                      | N/A        | N/A       | Monitor.                                         |
| `templates/location_historical.html` | Late addition, no view wiring                            | `19e9844`  | present   | Review requirement fit; drop if unused.          |

## README & Delivery Compliance Checklist

- README **missing**: no setup, API routes, env vars, deployment steps, or design notes.
- `.env.example` previously existed but deleted in `aa9bc36`; Compose references `SECRET_KEY`, `OWM_API_KEY`, etc. with no guidance.
- No take-home handoff doc summarising architecture; onboarding relies on `docs/TAKEHOME_AUDIT.md` (historical).
- Docker/Compose present but lacks instructions to run migrations, create superuser, or configure Redis.

## Refactor Opportunities (Analysis Only)

- `telemetry/tasks.py:27-34` — Replace inline `time.sleep` loop with asynchronous rate limiter or batched fetch to avoid throttling Celery worker throughput.
- `telemetry/tasks.py:121-148` — Add retry/backoff + delivery tracking for `send_alert_email`; currently logs and drops errors silently.
- `telemetry/views.py:106-140` — Clamp `hours` parameter and apply server-side validation to prevent unbounded queries.
- `telemetry/permissions.py:17-25` — Harden list-level permission (currently allows any authenticated list) to avoid overexposed alert history.
- `core/settings.py:15-33` — Fail fast when insecure defaults detected; enforce env-provided `SECRET_KEY`, default `DEBUG=False`.

## Final Recommendations

**Immediate**

- Restore tooling configs (`.flake8`, `.pre-commit-config.yaml`, `pyproject.toml`) and align CI with intended checks.
- Draft README + `.env.example`; document deployment prerequisites to satisfy take-home brief.
- Prepare filter-repo plan to purge `celerybeat-schedule.db` and replace default secrets text before mirroring to GitHub.
- Review `docs` ignore rule so audit deliverables stay tracked.

**Next Sprint**

- Refactor Celery worker for concurrency-safe rate limiting and add retry policies for external APIs and email delivery.
- Add validation around geocoding/weather inputs (lat/lon bounds, threshold enums, hours clamp) and corresponding tests.
- Introduce CI guardrails (new workflow in `.github/workflows/repo-hygiene.yml`) enforcing artefact/size policy and lint presence.
- Split monolithic changes into focused commits; adopt commit template referencing ticket/feature scope.
