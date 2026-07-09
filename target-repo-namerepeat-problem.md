# Plan: Fix "Could not create the target repository (422)" on Start Migration
 
## Context
Start Migration (OpenRewrite + push to Javaapex) is implemented and working. But
re-running a migration fails at repo creation with a **422**:
 
```
repo_creator | Creating repo Javaapex/registration-form-profile-Migrated20260708095604 (user)
start_migration | Migration failed: Could not create the target repository (422).
```
 
Root cause (confirmed via the GitHub API):
1. The frontend generates **one fixed target repo name** (timestamp captured when
   the wizard loads) and reuses it for every Start Migration in that session. The
   first attempt creates the repo; any retry collides — the repo already exists on
   Javaapex.
2. `RepoCreator._error_message` only inspects GitHub's top-level `message`
   ("Repository creation failed.") — the real reason ("name already exists on this
   account") lives in the nested `errors[]` array — so the collision is neither
   detected nor recovered from, and the whole migration hard-fails.
 
Decision (from the user): when the migrated code fails to build, **still publish**
(current behavior). So the only change needed is to make repo creation resilient to
name collisions. Build failures remain non-blocking.
 
## Fix (single file: `backend/app/infrastructure/github/repo_creator.py`)
- **Parse 422 correctly:** add a helper that reads the reason from
  `data["errors"][*]["message"]` (joined) plus the top-level `message`, so genuine
  errors surface a clear message and collisions are detectable.
- **Detect name-taken:** `_is_name_taken(response)` = status 422 and the reason text
  contains "already exists".
- **Uniquify + retry in `create()`:** attempt up to ~6 times. First attempt uses the
  requested name (keeps the nice name); on a name-taken response, generate a fresh
  candidate `f"{base}-{uuid4().hex[:5]}"` (base = the originally requested name) and
  retry. Return the `CreatedRepo` for whichever name succeeds (its real
  name/html_url/clone_url). Non-collision errors (401/403/404/other-422) raise
  immediately with the parsed reason. If every attempt somehow collides, raise
  `PushFailedError` with a clear message.
 
No changes needed elsewhere: `start_migration._publish` already uses the returned
`CreatedRepo.clone_url`/`html_url`, so `target_repo` reflects the actual created repo,
and the frontend reads `target_repo` from polling — the real (possibly suffixed)
name shows automatically. Reuse existing `settings.github_target_token`,
`ProfileResolver`, and `GithubClient.create_repository_sync`.
 
## Not changing
- Publish-on-build-failure stays (user chose "publish anyway"). The migration still
  completes and flags `buildSuccess=false`.
- The already-created `registration-form-profile-Migrated20260708095604` repo is left
  as-is (a legitimate earlier output; user can delete it if they want).
- No frontend changes.
 
## Verification
1. Unit: mock `GithubClient.create_repository_sync` to return a 422 name-taken body
   once, then 201 — assert `create()` retries with a suffixed name and returns the
   created repo. Also assert a non-collision 422 (e.g. invalid name) raises with the
   real `errors[]` message.
2. Real end-to-end: re-run a migration whose target name **already exists** on
   Javaapex (reproduce the reported collision) → confirm it now creates a uniquely
   suffixed repo, completes, and returns the new `target_repo`. Delete the test repo
   afterward.
3. Confirm the token is still masked in logs and `original-repo` untouched.
 
 