# CLAUDE.md — GymAssistantMcpServer

.NET 10 MCP server bridging GymAssistant API to Claude/Cursor/other MCP clients via Personal API Tokens.

## Language policy
- All docs and task notes: **Russian**
- All `AGENTS.md` and `CLAUDE.md` files: **English**

## General rules
- Tools are thin pass-throughs. Business logic stays on the backend; aggregation/reasoning happens in the LLM consuming this server.
- PAT-based auth only. No OAuth, no JWT in this server.
- stdio transport only in v0.1. HTTP/SSE in future.
- Never log the PAT. Prefix-only diagnostics if needed.

## Git rules
- Always ask for explicit confirmation before `git commit` or `git push`.
- Branch naming: `feature/<short-name>`.
- Every branch must have a task note in `docs/tasks/`.

## Build / run commands
- `dotnet build -c Release`
- `dotnet test -c Release`
- `docker build --secret id=ghuser,src=... --secret id=ghpat,src=... -t gymassistant-mcp:dev .`

## Key paths
| What | Path |
|---|---|
| Solution | `GymAssistantMcpServer.slnx` |
| Server project | `src/GymAssistant.McpServer/` |
| Tool implementations | `src/GymAssistant.McpServer/Tools/` |
| Infrastructure | `src/GymAssistant.McpServer/Infra/` |
| Tests | `tests/GymAssistant.McpServer.Tests/` |
| Dockerfile | `Dockerfile` |
| CI workflows | `.github/workflows/` |
| Plan/spec | (workspace-level `docs/superpowers/...`) |

## NuGet
- `GymAssistant.Client` — NSwag-generated, hosted at GitHub Packages (`nuget.pkg.github.com/Gym-Assistant`). Source name `gym` in `nuget.config`. Read access via user-level `~/.nuget/NuGet/NuGet.Config` locally; via `secrets.GITHUB_TOKEN` in CI.
- Lock file `packages.lock.json` is committed — Docker builds use `--locked-mode`.
- Pinned to `0.7.*` for reproducible builds.
