# GymAssistant MCP repository rules

## Scope and safety
- This repository has one supported Python MCP runtime in `integrations/local-gymassistant/`. `server.py` serves stdio; `remote_http.py` prepares Streamable HTTP with the same tools. Do not add a second implementation.
- Keep production data read-only during verification. Run writes only against isolated synthetic APIs. Never commit tokens, env files, user data, or backup files.
- Do not run `git commit`, `git push`, `git reset`, `git rebase`, or force-push unless the owner explicitly asks. Never add AI attribution to commit messages.
- Preserve existing client tool names and input contracts. If a legacy mutation cannot be made safe, keep its name with a clear fail-closed response and document the transition.
- Backend owns scopes, ownership, entitlement, and gift rules. Never infer access from a price or a local client flag. Remote transport must verify each user's own PAT on every request; no shared service PAT.
- Mutations are one HTTP attempt. A 5xx, timeout, or malformed success response is an unknown outcome; return IDs for readback. Never auto-retry a write.
- Do not activate a public HTTP endpoint or production billing gate from this repository without separately authorized deployment and backend evidence.

## Structure and checks
- `http_transport.py`: bounded HTTP, safe errors, per-request token support.
- `plan_tools.py`: safe new plan and optimistic append. `compat_tools.py`: historical names and guarded raw writes.
- `test_*.py`, `verify_stdio.py`, `verify_plans_stdio.py`: synthetic contract and real stdio checks.
- Task notes in `docs/tasks/` are Russian. `README.md` is a summary; `QUICKSTART.md` is the sole installation guide.
- Before handoff run the Python unit suite, both stdio scripts, fresh install, and relevant read-only checks on the current API. Keep hosted CI for this public repository; never send public forks to the owner's Mac.
