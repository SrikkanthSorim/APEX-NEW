# Java Migration Platform — Backend

FastAPI backend for the Java migration platform. Implements the **Connect**
(Step 1) and **Discovery** (Step 2) stages of the wizard.

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
