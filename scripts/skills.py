#!/usr/bin/env python3
"""Maintain the skills in this repository.

  scripts/skills.py new <name> "<description>"   scaffold a skill and list it in the README
  scripts/skills.py validate                     check every skill, the README and the manifests
  scripts/skills.py package [name ...]           zip skills into dist/ for upload to Claude.ai or ChatGPT
"""

import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / 'skills'
README = ROOT / 'README.md'
DIST = ROOT / 'dist'
VERSIONED_MANIFESTS = ['plugin.json', 'gemini-extension.json']
JSON_MANIFESTS = VERSIONED_MANIFESTS + ['.claude-plugin/marketplace.json']
TABLE_START = '<!-- skills:start -->'
TABLE_END = '<!-- skills:end -->'

NAME_RE = re.compile(r'^[a-z0-9]+(-[a-z0-9]+)*$')
KNOWN_FIELDS = {'name', 'description', 'license', 'compatibility', 'metadata', 'allowed-tools'}
MAX_LINES = 500

TEMPLATE = """---
name: {name}
description: {description}
license: MIT
---

# {title}

<!-- Instructions the agent follows once this skill is active. See CLAUDE.md for what belongs here. -->

## When to use

## Steps

1.

## Checks before finishing

-
"""


def parse_frontmatter(text):
    """Return the top-level keys of a SKILL.md frontmatter block, or None when there is none."""
    if not text.startswith('---\n'):
        return None
    end = text.find('\n---', 4)
    if -1 == end:
        return None

    fields = {}
    key = None
    for line in text[4:end].splitlines():
        match = re.match(r'^([A-Za-z][\w-]*):\s*(.*)$', line)
        if match:
            key, value = match.group(1), match.group(2).strip()
            fields[key] = '' if value in ('>', '|', '>-', '|-') else value.strip('\'"')
        elif key and line.startswith((' ', '\t')):
            fields[key] = (fields[key] + ' ' + line.strip()).strip()
    return fields


def skill_dirs():
    return sorted(p for p in SKILLS.iterdir() if p.is_dir()) if SKILLS.is_dir() else []


def readme_table():
    text = README.read_text()
    start, end = text.find(TABLE_START), text.find(TABLE_END)
    if -1 == start or -1 == end:
        sys.exit(f'README.md is missing the {TABLE_START} / {TABLE_END} markers')
    return text, start + len(TABLE_START), end


def validate():
    errors = []
    warnings = []

    versions = {}
    for manifest in JSON_MANIFESTS:
        try:
            data = json.loads((ROOT / manifest).read_text())
        except (OSError, json.JSONDecodeError) as e:
            errors.append(f'{manifest}: {e}')
            continue
        if manifest in VERSIONED_MANIFESTS:
            versions[manifest] = data.get('version')
    if 1 < len(set(versions.values())):
        errors.append(f'manifest versions differ: {versions}')

    _, start, end = readme_table()
    table = README.read_text()[start:end]

    for path in skill_dirs():
        rel = path.relative_to(ROOT)
        skill_md = path / 'SKILL.md'
        if not skill_md.is_file():
            errors.append(f'{rel}: missing SKILL.md')
            continue

        text = skill_md.read_text()
        fields = parse_frontmatter(text)
        if fields is None:
            errors.append(f'{rel}/SKILL.md: must start with a --- frontmatter block')
            continue

        name = fields.get('name', '')
        if name != path.name:
            errors.append(f'{rel}: frontmatter name "{name}" must equal the directory name')
        if not NAME_RE.match(path.name) or 64 < len(path.name):
            errors.append(f'{rel}: name must be 1-64 chars of a-z, 0-9 and single hyphens')

        description = fields.get('description', '')
        if not description:
            errors.append(f'{rel}: description is required')
        elif 1024 < len(description):
            errors.append(f'{rel}: description is {len(description)} chars, the limit is 1024')

        if 500 < len(fields.get('compatibility', '')):
            errors.append(f'{rel}: compatibility is over 500 chars')

        unknown = set(fields) - KNOWN_FIELDS
        if unknown:
            errors.append(f'{rel}: unknown frontmatter fields {sorted(unknown)}; put custom keys under metadata')

        if MAX_LINES < text.count('\n'):
            warnings.append(f'{rel}/SKILL.md: over {MAX_LINES} lines; move detail into references/')

        if f'skills/{path.name}/' not in table:
            errors.append(f'{rel}: not listed in the README skills table')

        for link in re.findall(r'\]\((?!https?://|#|mailto:)([^)\s]+)\)', text):
            if not (path / link.split('#')[0]).exists():
                errors.append(f'{rel}/SKILL.md: broken link {link}')

    for listed in re.findall(r'\]\(skills/([^/)]+)/?\)', table):
        if not (SKILLS / listed / 'SKILL.md').is_file():
            errors.append(f'README lists skills/{listed}/ but it does not exist')

    for w in warnings:
        print(f'warning: {w}')
    for e in errors:
        print(f'error: {e}')
    print(f'{len(skill_dirs())} skill(s) checked, {len(errors)} error(s)')
    return 1 if errors else 0


def new(name, description):
    if not NAME_RE.match(name) or 64 < len(name):
        sys.exit('name must be 1-64 chars of a-z, 0-9 and single hyphens')
    path = SKILLS / name
    if path.exists():
        sys.exit(f'{path.relative_to(ROOT)} already exists')

    path.mkdir(parents=True)
    title = name.replace('-', ' ').capitalize()
    (path / 'SKILL.md').write_text(TEMPLATE.format(name=name, description=description, title=title))

    text, start, end = readme_table()
    summary = description.split('. ')[0].rstrip('.')
    row = f'| [`{name}`](skills/{name}/) | {summary} |\n'
    table = text[start:end].rstrip('\n') + '\n' + row
    README.write_text(text[:start] + table + text[end:])

    print(f'created skills/{name}/SKILL.md and added it to README.md')
    return 0


def package(names):
    DIST.mkdir(exist_ok=True)
    targets = [SKILLS / n for n in names] if names else skill_dirs()
    for path in targets:
        if not (path / 'SKILL.md').is_file():
            sys.exit(f'{path.relative_to(ROOT)}: no SKILL.md')
        archive = DIST / f'{path.name}.zip'
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
            for file in sorted(path.rglob('*')):
                if file.is_file() and '.DS_Store' != file.name:
                    z.write(file, file.relative_to(path.parent))
        print(archive.relative_to(ROOT))
    return 0


def main(argv):
    if 2 <= len(argv) and 'validate' == argv[1]:
        return validate()
    if 4 == len(argv) and 'new' == argv[1]:
        return new(argv[2], argv[3])
    if 2 <= len(argv) and 'package' == argv[1]:
        return package(argv[2:])
    print(__doc__.strip())
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv))
