# RealTypeCoach local workflow

Use the `just` recipes in the repository root for common development tasks instead of ad-hoc shell commands.

## Core recipes

- `just sync-deps` — create or update `.venv` and install the project
- `just test <path> [args]` — run a focused pytest target
- `just test-all` — format, syntax-check, and run the full test suite
- `just install` — install the application into the local user environment
- `just run` — sync dependencies and start the application from the repo
- `just kill` — stop running RealTypeCoach instances
- `just status` — show whether RealTypeCoach is currently running
- `just monitor-log` — tail the application log

## Recommended change workflow

1. Run targeted checks with `just test ...` while iterating.
2. Run `just test-all` before finishing when the full suite is appropriate.
3. Use `just install` to apply repo changes to the installed app.
4. Use `just kill` and then `just run` when you need to restart the application from the repo checkout.
