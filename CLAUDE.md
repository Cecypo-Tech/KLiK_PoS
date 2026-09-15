# klik_pos

Bench-level instructions live in `~/frappe-bench/CLAUDE.md` (superpowers is the process
for every app in this bench). This file adds routing on top of that.

## Skill routing

Superpowers is the process (see `~/frappe-bench/.claude/rules/superpowers.md`).

- New feature or idea → `superpowers:brainstorming`, then `superpowers:writing-plans`
- Bug, error log, failing test → `superpowers:systematic-debugging` before any fix
- Implementing a written plan → `superpowers:executing-plans` (or
  `superpowers:subagent-driven-development` for independent tasks), with
  `superpowers:test-driven-development`
- Before landing → `superpowers:requesting-code-review`, then
  `superpowers:finishing-a-development-branch`
