#!/usr/bin/env python3
"""List everything in a Payum 1.x gateway package that a 2.x migration has to account for.

Reads PHP and composer.json files under the given directory and prints a Markdown inventory: the
factories and their config keys, every action with the requests it supports, the replies it throws and
the sub-requests it executes, status mapping, extensions, custom request classes, API classes, the keys
the gateway stores in a payment's details, and templates. It only reads files; it writes nothing and
makes no network calls.

The parsing is pattern based, so treat the result as a checklist to confirm by reading the code, not as
the final word.

Usage:
    inventory.py <gateway-dir> [--json]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SKIP_DIRS = {"vendor", "Tests", "tests", "node_modules", ".git"}

CORE_REQUESTS = {
    "Capture", "Authorize", "Refund", "Cancel", "Sync", "Payout", "Notify", "GetHumanStatus",
    "GetBinaryStatus", "GetStatusInterface", "Convert", "GetHttpRequest", "GetToken", "GetCurrency",
    "RenderTemplate", "ObtainCreditCard", "Generic",
}
MODEL_TYPES = {
    "ArrayAccess", "ArrayObject", "PaymentInterface", "PayoutInterface", "CreditCardInterface", "TokenInterface",
    "Traversable", "Countable", "IteratorAggregate",
}
OPERATION_REQUESTS = {
    "Capture": "CaptureHandlerInterface",
    "Authorize": "AuthorizeHandlerInterface",
    "Refund": "RefundHandlerInterface",
    "Cancel": "CancelHandlerInterface",
    "Sync": "SyncHandlerInterface",
    "Payout": "PayoutHandlerInterface",
    "Notify": "NotifyHandlerInterface",
}


def php_files(root: Path) -> list[Path]:
    return sorted(
        p for p in root.rglob("*.php") if not any(part in SKIP_DIRS for part in p.relative_to(root).parts)
    )


def strip_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", src)


def class_info(src: str) -> tuple[str | None, str | None, list[str]]:
    m = re.search(
        r"\b(?:abstract\s+|final\s+|readonly\s+)*class\s+(\w+)(?:\s+extends\s+([\w\\]+))?(?:\s+implements\s+([\w\\,\s]+))?\s*\{",
        src,
    )
    if not m:
        return None, None, []
    implements = [i.strip().split("\\")[-1] for i in (m.group(3) or "").split(",") if i.strip()]
    return m.group(1), (m.group(2) or "").split("\\")[-1] or None, implements


def method_body(src: str, name: str) -> str:
    m = re.search(r"function\s+" + name + r"\s*\([^)]*\)[^{]*\{", src)
    if not m:
        return ""
    depth, i = 1, m.end()
    while i < len(src) and depth:
        depth += {"{": 1, "}": -1}.get(src[i], 0)
        i += 1
    return src[m.end(): i - 1]


def uniq(items) -> list[str]:
    return sorted(set(items))


def composer(root: Path) -> dict:
    path = root / "composer.json"
    if not path.exists():
        for parent in root.parents:
            if (parent / "composer.json").exists():
                path = parent / "composer.json"
                break
        else:
            return {}
    data = json.loads(path.read_text())
    require = data.get("require", {})
    return {
        "file": str(path),
        "name": data.get("name"),
        "php": require.get("php"),
        "payum/core": require.get("payum/core"),
        "require": {k: v for k, v in require.items() if k not in ("php", "payum/core")},
        "require-dev": data.get("require-dev", {}),
    }


def config_keys(body: str) -> dict:
    keys: dict[str, str] = {}
    for m in re.finditer(r"'(payum\.[\w.]+)'\s*=>\s*(.{0,160})", body):
        value = m.group(2).strip()
        cls = re.search(r"new\s+([\w\\]+)|([\w\\]+)::class", value)
        keys[m.group(1)] = (cls.group(1) or cls.group(2)).split("\\")[-1] if cls else value.split("\n")[0][:80].rstrip(",")
    return keys


def options(body: str, key: str) -> list[str]:
    m = re.search(r"'" + re.escape(key) + r"'\]?\s*=\s*\[(.*?)\];", body, flags=re.S)
    if not m:
        m = re.search(r"'" + re.escape(key) + r"'\s*=>\s*\[(.*?)\]", body, flags=re.S)
    return [s.strip() for s in m.group(1).split(",") if s.strip()] if m else []


def analyse(root: Path) -> dict:
    out: dict = {
        "root": str(root), "composer": composer(root), "factories": [], "actions": [], "extensions": [],
        "requests": [], "apis": [], "other_classes": [], "state_keys": [], "templates": [],
        "tests": any((root / d).is_dir() for d in ("Tests", "tests")),
    }
    state_keys: set[str] = set()

    for path in php_files(root):
        rel = str(path.relative_to(root))
        src = strip_comments(path.read_text(errors="replace"))
        name, parent, implements = class_info(src)
        if not name:
            continue
        uses = uniq(t.split("\\")[-1] for t in re.findall(r"^\s*use\s+([\w\\]+Trait)\s*;", src, flags=re.M))

        for var in ("model", "details", "state"):
            state_keys.update(re.findall(r"\$" + var + r"\[\s*'([\w.-]+)'\s*\]", src))

        if parent == "GatewayFactory" or name.endswith("GatewayFactory"):
            body = method_body(src, "populateConfig")
            keys = config_keys(body)
            out["factories"].append({
                "file": rel, "class": name,
                "factory_name": keys.pop("payum.factory_name", None),
                "factory_title": keys.pop("payum.factory_title", None),
                "actions": {k: v for k, v in keys.items() if k.startswith("payum.action.")},
                "extensions": {k: v for k, v in keys.items() if k.startswith("payum.extension.")},
                "templates": {k: v for k, v in keys.items() if k.startswith(("payum.template.", "payum.paths"))},
                "other_keys": {k: v for k, v in keys.items()
                               if not k.startswith(("payum.action.", "payum.extension.", "payum.template.", "payum.paths"))},
                "default_options": options(body, "payum.default_options"),
                "required_options": options(body, "payum.required_options"),
                "builds_api": "payum.api" in body,
            })
            continue

        if "ActionInterface" in implements or parent in ("GatewayAwareAction", "BaseApiAwareAction") or rel.startswith("Action"):
            supports = method_body(src, "supports")
            execute = method_body(src, "execute")
            requests = uniq(re.findall(r"instanceof\s+([\w\\]+)", supports))
            requests = [r.split("\\")[-1] for r in requests]
            models = [r for r in requests if r in MODEL_TYPES]
            requests = [r for r in requests if r not in MODEL_TYPES]
            replies = uniq(r.split("\\")[-1] for r in re.findall(r"throw\s+new\s+([\w\\]*(?:Http\w+|Reply\w*))", src))
            sub = uniq(r.split("\\")[-1] for r in re.findall(r"->execute\(\s*(?:\$\w+\s*=\s*)?new\s+([\w\\]+)", src))
            marks = uniq(re.findall(r"->mark(\w+)\(", src))
            operation = next((r for r in requests if r in OPERATION_REQUESTS), None)
            kind = (
                "status" if marks or any(r.startswith("Get") and "Status" in r for r in requests)
                else "convert" if "Convert" in requests
                else "operation" if operation
                else "api-request" if rel.startswith("Action/Api") or any(r not in CORE_REQUESTS for r in requests)
                else "other"
            )
            out["actions"].append({
                "file": rel, "class": name, "kind": kind, "supports": requests, "models": models,
                "target_handler": OPERATION_REQUESTS.get(operation) if kind == "operation" else None,
                "replies_thrown": replies, "sub_requests": sub, "status_marks": marks, "traits": uses,
                "api_class": (re.search(r"apiClass\s*=\s*([\w\\]+)::class", src) or [None, None])[1],
                "constructor": re.sub(r"\s+", " ", (re.search(r"function\s+__construct\s*\(([^)]*)\)", src) or [None, ""])[1]).strip(),
                "lines": execute.count("\n"),
            })
            continue

        if "ExtensionInterface" in implements:
            hooks = [h for h in ("onPreExecute", "onExecute", "onPostExecute") if method_body(src, h).strip()]
            out["extensions"].append({"file": rel, "class": name, "hooks": hooks, "traits": uses})
            continue

        if rel.startswith("Request") or parent in ("Generic", "BaseModelAware", "BaseOrder"):
            out["requests"].append({"file": rel, "class": name, "extends": parent})
            continue

        if re.search(r"Api", name) or re.search(r"HttpClientInterface|MessageFactory|ClientInterface|SoapClient", src):
            ctor = re.search(r"function\s+__construct\s*\(([^)]*)\)", src)
            out["apis"].append({
                "file": rel, "class": name,
                "constructor": re.sub(r"\s+", " ", ctor.group(1)).strip() if ctor else "",
                "public_methods": uniq(m for m in re.findall(r"public\s+(?:static\s+)?function\s+(\w+)", src) if m != "__construct"),
                "http": uniq(re.findall(r"\b(HttpClientInterface|MessageFactory|StreamFactory|RequestFactoryInterface|ClientInterface|SoapClient|Psr18Client)\b", src)),
                "constants": uniq(re.findall(r"const\s+(\w+)", src))[:40],
            })
            continue

        out["other_classes"].append({
            "file": rel, "class": name, "extends": parent, "implements": implements,
            "constants": len(re.findall(r"\bconst\s+\w+", src)),
        })

    out["state_keys"] = sorted(state_keys)
    for ext in ("twig", "html", "php"):
        out["templates"] += [str(p.relative_to(root)) for p in root.rglob(f"*.{ext}")
                             if "views" in p.parts or "templates" in p.parts]
    out["templates"] = sorted(set(out["templates"]))
    return out


def md(inv: dict) -> str:
    lines = [f"# Inventory of `{inv['root']}`", ""]
    c = inv["composer"]
    lines += ["## Package", "",
              f"- composer: `{c.get('file', 'not found')}` ({c.get('name')})",
              f"- php: `{c.get('php')}`, payum/core: `{c.get('payum/core')}`",
              f"- other requires: {', '.join(f'`{k}:{v}`' for k, v in c.get('require', {}).items()) or 'none'}",
              f"- tests directory: {'yes' if inv['tests'] else 'no'}", ""]

    lines += ["## Factories", ""]
    for f in inv["factories"]:
        lines += [f"### {f['class']} (`{f['file']}`)", "",
                  f"- factory_name: {f['factory_name']}, factory_title: {f['factory_title']}",
                  f"- default_options: {', '.join(f['default_options']) or 'none'}",
                  f"- required_options: {', '.join(f['required_options']) or 'none'}",
                  f"- builds payum.api: {f['builds_api']}"]
        for group in ("actions", "extensions", "templates", "other_keys"):
            if f[group]:
                lines.append(f"- {group}: " + ", ".join(f"`{k}` -> {v}" for k, v in f[group].items()))
        lines.append("")

    lines += ["## Actions", "", "| Action | Kind | Supports | Target | Throws | Executes | Marks |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for a in inv["actions"]:
        lines.append("| `{}` | {} | {} | {} | {} | {} | {} |".format(
            a["file"], a["kind"], ", ".join(a["supports"] + [f"model: {m}" for m in a["models"]]) or "?", a["target_handler"] or "",
            ", ".join(a["replies_thrown"]), ", ".join(a["sub_requests"]), ", ".join(a["status_marks"])))
    lines.append("")
    by_handler: dict[str, list[str]] = {}
    for a in inv["actions"]:
        if a["target_handler"]:
            by_handler.setdefault(a["target_handler"], []).append(a["class"])
    shared = {h: c for h, c in by_handler.items() if len(c) > 1}
    if shared:
        lines += ["Several actions answer the same operation, and 2.x allows one handler per command: "
                  + "; ".join(f"{h} <- {', '.join(c)}" for h, c in shared.items()), ""]
    legacy = [a for a in inv["actions"] if {"ApiAwareTrait", "GenericTokenFactoryAwareTrait"} & set(a["traits"])]
    if legacy:
        lines += ["Actions using deprecated awareness traits: " + ", ".join(f"`{a['class']}` ({', '.join(a['traits'])})" for a in legacy), ""]

    for title, key, fmt in (
        ("Extensions", "extensions", lambda e: f"- `{e['file']}`: hooks {', '.join(e['hooks']) or 'none'}"),
        ("Custom requests", "requests", lambda r: f"- `{r['file']}` extends {r['extends']}"),
        ("API classes", "apis", lambda a: f"- `{a['file']}`: __construct({a['constructor']}); http: {', '.join(a['http']) or 'none'}; public: {', '.join(a['public_methods'])}"),
        ("Other classes", "other_classes", lambda o: f"- `{o['file']}`: extends {o['extends']}, implements {', '.join(o['implements']) or 'nothing'}, {o['constants']} constants"),
    ):
        lines += [f"## {title}", ""] + ([fmt(x) for x in inv[key]] or ["none"]) + [""]

    lines += ["## Keys stored in payment details", "",
              ", ".join(f"`{k}`" for k in inv["state_keys"]) or "none", "",
              "## Templates", "", "\n".join(f"- `{t}`" for t in inv["templates"]) or "none", ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], epilog=__doc__.split("\n\n", 1)[1],
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("gateway_dir", type=Path, help="the directory holding the gateway's src (or the package root)")
    parser.add_argument("--json", action="store_true", help="print JSON instead of Markdown")
    args = parser.parse_args()
    if not args.gateway_dir.is_dir():
        print(f"{args.gateway_dir} is not a directory", file=sys.stderr)
        return 2
    inv = analyse(args.gateway_dir.resolve())
    print(json.dumps(inv, indent=2) if args.json else md(inv))
    return 0


if __name__ == "__main__":
    sys.exit(main())
