# klik_pos

Bench-level instructions live in `~/frappe-bench/CLAUDE.md` (gstack is required for all
AI-assisted work in this repo). This file adds routing on top of that.

## Skill routing

When the user's request matches an available skill, invoke it via the Skill tool. When in doubt, invoke the skill.

Key routing rules:
- Architecture → invoke /plan-eng-review
- Design system/plan review → invoke /design-consultation or /plan-design-review
- Bugs/errors → invoke /investigate
- QA/testing site behavior → invoke /qa or /qa-only
- Code review/diff check → invoke /review
- Visual polish → invoke /design-review
- Ship/deploy/PR → invoke /ship or /land-and-deploy
- Author a backlog-ready spec/issue → invoke /spec
- Save progress → invoke /context-save
- Resume context → invoke /context-restore
