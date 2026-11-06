# Payum agent skills

Skills that teach AI coding agents how to integrate [Payum](https://github.com/Payum/Payum), the
framework-agnostic PHP payment library: setting up gateways, taking payments, handling webhooks and
storing payment state.

Each skill is a folder with a `SKILL.md` file in the open [Agent Skills](https://agentskills.io) format,
so the same files work in Claude, Codex, Cursor, Gemini CLI, GitHub Copilot and the other agents that
support the standard. An agent loads only a skill's name and description up front and reads the rest
when your request matches it.

## Skills

<!-- skills:start -->
| Skill | What it does |
|-------|--------------|
<!-- skills:end -->

## Install

### Any agent: the `skills` CLI

The quickest route for most agents. It detects which agents you have installed and copies the skills
into each one's skills folder. Needs Node.js 22.20 or later.

```bash
npx skills add Payum/agent-skills              # pick skills and agents interactively
npx skills add Payum/agent-skills --list       # see what is available
npx skills add Payum/agent-skills --skill <name> -a claude-code
```

Add `-g` to install for your user instead of the current project.

### Claude Code

Install as a plugin, so `/plugin` keeps the skills up to date:

```
/plugin marketplace add Payum/agent-skills
/plugin install payum@payum
```

### Gemini CLI

```bash
gemini extensions install https://github.com/Payum/agent-skills
gemini extensions update payum    # later, to pick up new skills
```

### Codex, Cursor, GitHub Copilot, OpenCode, Windsurf and others

Use the `skills` CLI above. To install by hand, copy a skill folder into your project's
`.agents/skills/` directory, which most agents read (Claude Code reads `.claude/skills/`):

```bash
git clone https://github.com/Payum/agent-skills
cp -r agent-skills/skills/<name> your-project/.agents/skills/
```

### Claude.ai, Claude Desktop and ChatGPT

These apps take a skill as a zip upload. Download the skill's zip from the
[latest release](https://github.com/Payum/agent-skills/releases/latest) and upload it from the Skills
section of the app's settings. Upload one zip per skill.

## Contributing

Read [CLAUDE.md](CLAUDE.md) before adding or changing a skill; it lists what every skill needs. In
short:

```bash
python3 scripts/skills.py new <name> "<what it does and when to use it>"
# write skills/<name>/SKILL.md
python3 scripts/skills.py validate
```

Skills run with the permissions of whoever installs them. Read a skill's `SKILL.md` and any scripts it
ships before installing it, here or anywhere else.

## License

MIT. See [LICENSE](LICENSE).
