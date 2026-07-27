# Java Migration Platform — Backend

FastAPI backend for the Java migration platform. Implements **Connect** (Step 1),
**Discovery** (Step 2), **Migration Config** (Step 4 destination), and
**Start Migration** (OpenRewrite migration + publish to GitHub).

> **Start Migration prerequisites (local):** JDK 21 + Maven on PATH (Gradle uses
> each project's `gradlew`). Set `GITHUB_TARGET_TOKEN` (authorized on the target
> owner) and `GITHUB_TARGET_OWNER` in `.env`.

### Start Migration — `POST /api/v1/migration/{jobId}/start`
Copies `original-repo` → `migrated-repo`, runs OpenRewrite (UpgradeToJava{target}
+ `javax`→`jakarta`) via Maven/Gradle, then creates a new repo under the target
owner and pushes the result. Async (background thread); poll:
`GET /api/v1/migration/{jobId}/summary` · `/detail` · `/logs`. Terminal statuses:
`completed | failed`. The migrated code is published to
`https://github.com/<owner>/<targetRepoName>` (returned as `target_repo`).
Recipe/plugin versions are pinned in `core/config.py`. Tokens are masked in logs.

## Connect stage

`POST /api/v1/connect` validates a GitHub repository URL, detects whether the
repo is **PUBLIC** or **PRIVATE**, verifies access, creates a unique `jobId`,
and stores a connect report locally. It does **not** clone the repository or run
any migration — that happens in later stages.

### Request

```json
{
  "repoUrl": "https://github.com/owner/repo",
  "githubToken": "optional-token"
}
```

### Success response

```json
{
  "jobId": "job_ab12cd34ef56",
  "repoUrl": "https://github.com/owner/repo",
  "owner": "owner",
  "repoName": "repo",
  "repoVisibility": "PUBLIC",
  "accessStatus": "ACCESS_GRANTED",
  "message": "Repository access verified successfully."
}
```

### Error responses

| accessStatus  | HTTP | When                                                        |
| ------------- | ---- | ----------------------------------------------------------- |
| INVALID_URL   | 400  | URL is not a recognizable github.com repository             |
| ACCESS_DENIED | 403  | Private repo without a valid token, or invalid token        |
| NOT_FOUND     | 404  | Repo does not exist / token lacks access                    |
| SERVICE_ERROR | 502  | GitHub could not be reached                                 |

### Stored artifact

On success a report is written to:

```
storage/migration-jobs/<jobId>/reports/connect-report.json
```

## Discovery stage

`POST /api/v1/discovery/{jobId}` reads the job's connect report, clones the repo
into `original-repo` (read-only), and analyzes the project. It does **not** run
any migration, OpenRewrite, Maven/Gradle build, or push — and never modifies the
cloned repo. An optional `{ "githubToken": "..." }` body overrides the token for
private repos (otherwise the token stored during Connect is used).

Detects: build tool (Maven/Gradle/unsupported), Java version, Spring Boot
version, project type (Spring Boot / Spring MVC / Servlet-JSP / plain Java),
single vs multi-module, dependencies, and frontend presence (React / Angular /
Vite / JSP).

### Error statuses

| status                   | HTTP | When                                            |
| ------------------------ | ---- | ----------------------------------------------- |
| CONNECT_REPORT_NOT_FOUND | 404  | No connect report — Connect step not completed  |
| CLONE_FAILED             | 502  | Repository could not be cloned (access/network) |
| UNSUPPORTED_PROJECT      | 422  | No Maven or Gradle build file found in the root  |

### Artifacts (after success)

```
storage/migration-jobs/<jobId>/
    original-repo/                     # read-only clone (untouched)
    reports/discovery-report.json
    logs/discovery.log                 # clone log (tokens masked)
```

## Unit test analysis / generation / execution / coverage

Populates the Result page's "Unit Test Report" card grid with real data: an
OpenRewrite LST scan of the repo (never regex/filename-only) detects existing
tests right after Discovery clones the repo; if `runTests` is enabled in
Migration Config, Start Migration compiles/runs the existing suite and produces
JaCoCo coverage. Missing-test generation is intentionally separate and runs only
when `use_llm_tests` / `useLlmTests` is enabled.

Generation includes every concrete eligible class by default:
`SERVICE`/`VALIDATOR`/`CONVERTER`/`UTILITY`/`DOMAIN` plus
`CONTROLLER`/`ENTITY`/`OTHER` classes that have at least one non-accessor
method (`GENERATION_ELIGIBLE_CLASS_TYPES` in
`app/domain/models/unit_test_report.py`). Each candidate is bounded by
`UNIT_TEST_CLASS_TIMEOUT_SECONDS`, the whole batch by
`UNIT_TEST_GENERATION_TOTAL_TIMEOUT_SECONDS`, and a Groq rate limit (HTTP
429) falls back to deterministic JUnit contract tests generated from the
OpenRewrite inventory instead of producing zero files.
**Maven, single-module projects only in this phase** — Gradle and
multi-module reactors report an honest "not yet supported" status instead of
a fabricated number.

Test generation is backed by Groq's Chat Completions API (see
`app/infrastructure/llm/groq_client.py`), behind the provider-agnostic
`UnitTestLlmClient` interface (`app/domain/llm/llm_client.py`) so another
provider could be swapped in later. A Groq API failure (missing key, auth,
rate limit, timeout, malformed response) is recorded as a structured
generation failure and never blocks existing-test execution or the rest of
the migration — see `GenerateUnitTestsUseCase`.

### Timeouts, retries, and rate-limit fallback

- **Per-call**: `GroqClient` uses split connect/read timeouts
  (`GROQ_CONNECT_TIMEOUT_SECONDS` / `GROQ_READ_TIMEOUT_SECONDS`) and retries a
  transient failure (timeout, 429, 500, 502, 503, 504) up to
  `UNIT_TEST_GENERATION_MAX_RETRIES` times internally, with a capped
  exponential/`Retry-After`-aware backoff between attempts. A non-retryable
  failure (400/401/402/403/404, invalid key, invalid request) never retries.
- **Per-class**: `GenerateUnitTestsUseCase` never retries a failure GroqClient
  already retried internally (that would multiply wait time for no benefit)
  -- it only retries a *malformed/unusable response* (invalid JSON/schema),
  bounded by `UNIT_TEST_MAX_REPAIR_ATTEMPTS`, the same budget used for
  validation/compile repair. Bounded by `UNIT_TEST_CLASS_TIMEOUT_SECONDS`
  overall; a call already in flight is never cut off before one legitimate
  attempt's own ceiling, but never past what's left of the total batch
  budget either.
- **Per-batch**: bounded by `UNIT_TEST_GENERATION_TOTAL_TIMEOUT_SECONDS`
  regardless of how many classes remain.
- **Rate-limit fallback**: when Groq is still rate-limited after GroqClient's
  own retry, the use case generates deterministic JUnit 5 contract tests from
  the OpenRewrite class/method inventory. These fallback tests still pass
  through the normal validation, write, compile, and run acceptance gate before
  they count as generated files.

### One-time setup: build the OpenRewrite analysis tool

```bash
mvn -f tools/rewrite-test-inventory/pom.xml package
```

Requires JDK 17+ on the machine running the backend (a separate JDK from
whatever `mvn`/`gradle` use for the migration itself is fine — see
`app/infrastructure/testing/rewrite_inventory_tool.py`, which auto-discovers
one). Produces `tools/rewrite-test-inventory/target/rewrite-test-inventory.jar`.
Until this is built, unit-test analysis/generation endpoints return a clear
`TOOL_UNAVAILABLE` error instead of silently doing nothing.

### Endpoints (`/api/v1/migration/{jobId}/unit-tests/...`)

`analyze` · `generate` · `run` · `rerun` · `status` · `report` ·
`report/download` (HTML) · `generated-files`. All require the authenticated
job owner (`verify_job_ownership`), matching every other job-scoped route.

### Relevant environment variables (see `core/config.py` for defaults)

| Variable | Purpose |
| --- | --- |
| `UNIT_TEST_EXECUTION_ENABLED` | Master switch for the whole pipeline |
| `UNIT_TEST_GENERATION_MAX_CLASSES` | Optional cap on classes generated per migration job. Unset by default, so every eligible class gets generation; set an integer only when a deployment needs a hard cap |
| `UNIT_TEST_MAX_CASES_PER_CLASS` | Cap on generated test methods per class |
| `UNIT_TEST_MAX_REPAIR_ATTEMPTS` | Bounded LLM repair-loop attempts on an invalid response, failed validation, or a compile failure |
| `UNIT_TEST_GENERATION_MAX_RETRIES` | Bounded caller-level retry count *inside GroqClient* for a single Groq call on a temporary error (timeout, 429, 500, 502, 503, 504). Default `1`. Never retried again by the use case on top of this. Never retries 400/401/402/403/404, an invalid API key, or an invalid request |
| `UNIT_TEST_CLASS_TIMEOUT_SECONDS` | Hard wall-clock ceiling (default `180`) on the Groq calls spent generating tests for one class. A call already in flight is never cut off before `GROQ_CONNECT_TIMEOUT_SECONDS + GROQ_READ_TIMEOUT_SECONDS` has elapsed, but never past the remaining total-batch budget either. Exceeded -> that class is marked `GENERATION_TIMEOUT` and generation moves on; never waits indefinitely |
| `UNIT_TEST_GENERATION_TOTAL_TIMEOUT_SECONDS` | Hard wall-clock ceiling (default `1800`) for the *entire* generation batch across every candidate class. Exceeded -> remaining classes are skipped (`generationStatus=TIME_BUDGET_EXCEEDED`) and the migration continues (existing-test execution, JaCoCo, quality gates, GitHub push are never blocked) |
| `JACOCO_MAVEN_PLUGIN_VERSION` | Pinned JaCoCo plugin version (CLI-invoked, no pom.xml edits) |
| `GROQ_API_KEY` | Required for test generation — get one at console.groq.com/keys. Leave empty to disable generation (existing-test analysis/execution still runs) |
| `GROQ_MODEL` | Chat model used for generation (default `llama-3.3-70b-versatile`) |
| `GROQ_CONNECT_TIMEOUT_SECONDS` / `GROQ_READ_TIMEOUT_SECONDS` | Separate connect vs. response-read timeouts (default `10` / `60`) applied to the underlying httpx client -- a slow/unreachable host fails fast on connect without cutting a legitimately-streaming response short. Read is 60s because a strict-JSON-schema structured completion from this model measurably takes 45s+ |
| `GROQ_MAX_COMPLETION_TOKENS` | Max response tokens per Groq call (default `5000` -- trimmed from 8000 since constrained JSON-schema decoding gets slower as the budget grows, and a generated test class rarely needs that many tokens) |

## Architecture (layered)

```
api/v1/endpoints/connect_controller.py   HTTP boundary (thin)
application/pipelines/connect_pipeline.py orchestration seam
application/use_cases/connect_repository.py URL validation, job creation, persistence
infrastructure/github/github_client.py    GitHub REST calls
infrastructure/github/repo_access_checker.py public/private/access detection
infrastructure/persistence/job_repository.py local job storage
core/config.py, core/exceptions.py        settings & domain errors
shared/response_builder.py                response shaping

# Discovery
api/v1/endpoints/discovery_controller.py  HTTP boundary (thin, threadpool)
application/pipelines/discovery_pipeline.py orchestration seam
application/use_cases/run_discovery.py    validate → clone → analyze → persist
infrastructure/git/repository_cloner.py   git clone (token-masked logging)
infrastructure/git/git_command_runner.py  git invocation
infrastructure/workspace/*                workspace folders & path layout
infrastructure/analyzers/project_analyzer.py coordinates the detectors below
infrastructure/analyzers/*_detector.py    build tool, java version, spring boot,
                                          dependencies, modules, project type, frontend
shared/command_runner.py, file_utils.py, json_utils.py  shared utilities

# Unit tests
api/v1/endpoints/unit_test_controller.py  HTTP boundary (thin, threadpool)
application/pipelines/unit_test_pipeline.py orchestration seam
application/use_cases/analyze_unit_tests.py   OpenRewrite LST inventory + decision
application/use_cases/generate_unit_tests.py  Groq generation + validation + repair loop
application/use_cases/run_unit_tests.py       compile/execute + JaCoCo coverage
application/services/unit_test_report_service.py shape persisted report -> API contract
application/services/unit_test_html_report.py    downloadable HTML report
domain/llm/llm_client.py                         provider-agnostic LLM contract + schemas
infrastructure/llm/groq_client.py                Groq Chat Completions client (retries/error mapping)
infrastructure/testing/rewrite_inventory_tool.py invokes tools/rewrite-test-inventory jar
infrastructure/testing/rewrite_test_validator.py validates LLM output before writing files
infrastructure/testing/class_selector.py         prioritize/skip class selection
infrastructure/testing/maven_test_runner.py      mvn test + JaCoCo (CLI-only, no pom edits)
infrastructure/testing/surefire_report_parser.py real pass/fail/skip counts from XML
infrastructure/testing/jacoco_report_parser.py   real coverage % from XML
tools/rewrite-test-inventory/                    standalone OpenRewrite Java CLI (own pom.xml)
```

## Run locally

```bash
pip install -r requirements.txt
```

Then start the server with the helper script (recommended — it frees the port
of any stale/orphaned server first, so you never end up with an old process
silently serving on a port your new one can't bind):

```powershell
./run.ps1            # port 8000, reload watching app/ only
./run.ps1 -Port 8001
./run.ps1 -NoReload  # single process, no file watching
```

Or run uvicorn directly:

```bash
uvicorn app.main:app --reload --reload-dir app --port 8000
```

> **Two things that will bite you without the right flags / clean shutdown:**
> 1. Use `--reload-dir app` (watch only source). Without it the watcher also
>    watches `storage/`, so cloning a repo during Discovery restarts the server
>    mid-clone → 502. `run.ps1` already does this.
> 2. Stop the server with **Ctrl+C** (clean shutdown). On Windows `--reload`
>    runs a supervisor + worker child; force-killing/closing the window can
>    orphan the worker, which keeps holding the port and serving old code.
>    `run.ps1` clears such orphans on the next start.

Health check: `GET /health`. Interactive docs: `http://localhost:8000/docs`.

Configuration is via environment variables / `.env` (see `.env` for the
available keys: `GITHUB_API_BASE_URL`, `GITHUB_TOKEN`, `CORS_ORIGINS`, ...).
