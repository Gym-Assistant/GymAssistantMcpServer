# AGENTS.md

Rules for AI coding agents working in this repo.

## Scope and safety
- Keep changes minimal and task-focused.
- Never commit secrets (PATs, Docker Hub tokens). Use repo secrets or local env.
- Do not run `git commit`, `git push`, `git reset`, `git rebase`, or force-push unless explicitly asked.
- Do not touch generated/build output (`bin/`, `obj/`, `.docker-buildx-cache/`).

## Branching and task notes
- Create new branches using `feature/<short-name>`.
- Every branch/task must have a short write-up in `docs/tasks/` (Context / Current State / Plan / Done / Verification).

## Architecture & boundaries
- Tools live in `src/GymAssistant.McpServer/Tools/{Resource}Tools.cs`. One file per resource group.
- Tools must be thin pass-throughs to `GymAssistant.Client`. No business logic, no aggregation, no caching.
- Infra in `src/GymAssistant.McpServer/Infra/`. Three responsibilities: env config, http auth handler, client factory.
- All `Console.Write*` goes to stderr only. stdout is the MCP transport — writing there breaks the protocol.

## Coding conventions
- .NET 10, nullable enabled, implicit usings.
- Each tool method has `[McpServerTool(Name = "...")]` and `[Description("...")]`.
- Tool names: `snake_case`, no `gym_` prefix (MCP client adds server-name prefix automatically).
- Tool descriptions: Russian short description + key English API terms in parentheses if applicable. Mention required scope.
- DTO and method names from `GymAssistant.Client` come from NSwag — don't rename, follow whatever the generated client exposes.
- The NSwag client class is `GymAssistant.Client.Client`, aliased project-wide as `GymClient` (via `<Using Alias>` in csproj).

## Pre-flight checks (before handing off)
- `dotnet build -c Release` — 0 errors, 0 warnings
- `dotnet test -c Release` — all pass (reflection-based smoke tests in `tests/`)
- `docker build .` succeeds (need `GITHUB_PACKAGES_PAT` / user-level nuget.config for restore)
- Manual `claude mcp add` against local docker image — `health_check` returns ok
