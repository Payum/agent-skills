# CLAUDE.md

Guidance for agents (and people) working in this repository. `AGENTS.md` is a symlink to this file, so
Codex, Cursor, Copilot and other agents read the same rules.

## What this repository is

Published agent skills that help developers integrate [Payum](https://github.com/Payum/Payum) into their
own applications. The audience is a developer using Payum for the first time, through their AI agent. A
skill is not documentation of Payum's internals and not a tool for working on Payum itself.

Every skill lives in `skills/<name>/` and follows the [Agent Skills specification](https://agentskills.io/specification).
That one folder serves every agent; the manifests at the root only tell each tool where to find it.

```
skills/<name>/SKILL.md            the skill (required)
skills/<name>/references/*.md     detail the agent reads on demand (optional)
skills/<name>/scripts/            code the agent runs (optional)
skills/<name>/assets/             templates and files the skill copies (optional)
.claude-plugin/marketplace.json   Claude Code marketplace; the repo root is the "payum" plugin
plugin.json                       Agent Plugins manifest read by Codex and Cursor
gemini-extension.json             Gemini CLI extension manifest
scripts/skills.py                 new / validate / package
.github/workflows/                validate on every push and PR; attach zips to each release
```

Skills are discovered from `skills/` by every tool, so adding a skill never touches a manifest. Do not
add per-agent copies of a skill, a `skills` field to a manifest, or agent-specific folders such as
`.cursor/skills`. Do not rename the Claude marketplace to `agent-skills`; Claude Code reserves that name.

## Adding a skill

1. `python3 scripts/skills.py new <name> "<description>"`. It creates `skills/<name>/SKILL.md` from a
   template and adds a row to the skills table in `README.md`.
2. Write the skill (see below).
3. Edit the README row so the "What it does" column is one plain sentence a user can scan.
4. `python3 scripts/skills.py validate` must pass. CI runs the same check.
5. Test it in at least one agent (see "Testing a skill").
6. Bump the version (see "Releasing") in the same pull request.

Changing or removing a skill follows the same rules: the README table must match `skills/` exactly, and
the validator fails if a row points at a missing skill or a skill has no row.

## Requirements for every skill

**Frontmatter.** Only the fields in the spec: `name`, `description`, and optionally `license`,
`compatibility`, `metadata`, `allowed-tools`. Put anything custom under `metadata`.

- `name`: lowercase letters, digits and single hyphens, 1-64 characters, equal to the folder name. Prefix
  it with `payum-` so it stays unambiguous next to a user's other skills (`payum-stripe-checkout`, not
  `stripe-checkout`).
- `description`: at most 1024 characters, written in the third person. It is the only part an agent
  sees before deciding to load the skill, so say what the skill does *and* when to use it, naming the
  words a user would actually type ("Stripe", "webhook", "Symfony", "refund"). Say when *not* to use it
  if a neighbouring skill is easy to confuse with it.
- `compatibility`: set it when the skill needs something specific, e.g.
  `Payum 2.x, PHP 8.1+, Composer`. Most skills should state the Payum version they target.

**Body.**

- Under 500 lines. Move long reference material (option tables, full examples, per-framework variants)
  into `references/` and link to it from `SKILL.md` with a relative link, saying when to read it.
- Write instructions for the agent, in the imperative: what to check in the user's project first, the
  steps in order, and how to confirm the result. End with a short checklist the agent runs before it
  says it is done.
- Detect before you assume. Tell the agent how to find the user's framework (Symfony bundle, Laravel
  package, plain PHP), Payum version (`composer show payum/core`) and existing gateway config, and
  branch on what it finds.
- Every code sample must run against the Payum version the skill targets. Check it against the Payum
  source, not from memory: class names, method signatures and config keys change between 1.x and 2.x.
- Prefer Payum 2.x APIs. Do not teach anything Payum has deprecated (for example `ApiAwareInterface`
  or `payum.api.*` config) except in a skill whose job is migrating away from it.
- Never put real credentials, API keys or webhook secrets in a skill. Use sandbox placeholders and tell
  the agent to read secrets from the environment.
- Scripts under `scripts/` must be safe to run unattended: no network calls the skill does not explain,
  nothing that writes outside the user's project, and a `--help` that says what they do.
- One skill, one job. If a skill grows a second unrelated workflow, split it.

## Testing a skill

The validator checks structure only. Before opening a pull request, install the skill locally and give
an agent a realistic request that should trigger it, in a throwaway project with Payum installed:

- Claude Code: `claude --plugin-dir .` from this repository, or copy the folder to
  `<project>/.claude/skills/`.
- Other agents: `npx skills add ./ --skill <name>` from inside the test project, or copy the folder to
  `<project>/.agents/skills/`.

Check that the agent picks the skill up from the description alone, follows it, and ends with working
code. Also try one request that should *not* trigger it.

## Releasing

The version lives in `plugin.json` and `gemini-extension.json` and must be identical in both; the
validator enforces it. Use semver: a new skill is a minor bump, a fix to an existing one is a patch.

1. Bump both versions on the release branch.
2. Tag `vX.Y.Z` and publish a GitHub release for it.
3. The `release` workflow runs `scripts/skills.py package` and attaches one zip per skill to the
   release, which is what Claude.ai and ChatGPT users upload.

Claude Code, Gemini CLI and the `skills` CLI install straight from the default branch, so anything
merged is live for them immediately. Keep the default branch releasable.

## Writing style

Skills, the README and this file follow the same rules as Payum's own docs: plain language, the action
first, a caveat only where a user would otherwise get it wrong. Comments in scripts are minimal and never
narrate a change or refer to a discussion.
