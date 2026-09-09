#!/usr/bin/env python3
"""Render an agent execution plan from a deck/default selection JSON."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def selections_from(doc: dict[str, Any]) -> tuple[dict[str, str], dict[str, str]]:
    if "selections" in doc and isinstance(doc["selections"], dict):
        return dict(doc["selections"]), dict(doc.get("notes", {}))
    selected = doc.get("selected_decisions")
    if isinstance(selected, list):
        choices, notes = {}, {}
        for item in selected:
            choices[item["decision_id"]] = item["option_id"]
            if item.get("note"):
                notes[item["decision_id"]] = item["note"]
        return choices, notes
    raise ValueError("selection JSON must contain selections{} or selected_decisions[]")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    decision_doc = load(ROOT / "machine" / "decisions.json")
    task_doc = load(ROOT / "machine" / "agent-task-manifest.json")
    selection_doc = load(args.selection)
    selected, notes = selections_from(selection_doc)

    decisions = {d["id"]: d for d in decision_doc["decisions"]}
    missing = set(decisions) - set(selected)
    if missing:
        defaults = load(ROOT / "machine" / "default-selections.json")["selections"]
        for did in missing:
            selected[did] = defaults[did]

    lines = [
        "# extract-api plan from selected decisions",
        "",
        f"- Repository: `{decision_doc['snapshot']['repository']}`",
        f"- Review snapshot: `{decision_doc['snapshot']['snapshot_sha']}`",
        f"- Selection source: `{args.selection}`",
        "",
        "## Selected decisions",
        "",
    ]
    agent_actions: list[str] = []
    human_actions: list[str] = []
    for did in sorted(decisions):
        d = decisions[did]
        option = next((o for o in d["options"] if o["id"] == selected[did]), None)
        if option is None:
            raise ValueError(f"unknown option {selected[did]!r} for {did}")
        marker = "recommended" if option["id"] == d["recommended"] else "custom"
        lines += [f"### {did}: {d['title']}", "", f"**Selected:** {option['label']} ({marker})", "", option["summary"], "", f"**Trade-off:** {option['tradeoffs']}"]
        if notes.get(did):
            lines += ["", f"**Owner note:** {notes[did]}"]
        lines.append("")
        agent_actions.extend(option.get("agent_actions", []))
        human_actions.extend(option.get("human_actions", []))

    lines += ["## Decision-derived human actions", ""]
    for action in dict.fromkeys(human_actions):
        lines.append(f"- {action}")
    if not human_actions:
        lines.append("- None declared")
    lines += ["", "## Decision-derived agent actions", ""]
    for action in dict.fromkeys(agent_actions):
        lines.append(f"- {action}")
    if not agent_actions:
        lines.append("- None declared")

    by_wave: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for task in task_doc["tasks"]:
        by_wave[task["wave"]].append(task)
    lines += ["", "## Dependency-aware execution queue", ""]
    for wave in sorted(by_wave):
        lines += [f"### {wave}", ""]
        for task in by_wave[wave]:
            deps = ", ".join(task["depends_on"]) or "none"
            paid = "; PAID HUMAN GATE" if task.get("paid") else ""
            lines += [f"- **{task['id']}  -  {task['title']}** ({task['owner']}, {task['priority']}{paid})", f"  - Depends on: {deps}"]
            for criterion in task["acceptance"]:
                lines.append(f"  - Done when: {criterion}")
        lines.append("")

    lines += [
        "## Operating constraints",
        "",
        "- Revalidate current HEAD before applying snapshot-derived actions.",
        "- No paid call without explicit run-scoped approval and spend cap.",
        "- No agent-only DRAFT-to-REVIEWED promotion.",
        "- No autonomous weakening/self-certification of agent safety guards.",
        "- Preserve strict/fail-loud contracts and avoid pre-evidence scope expansion.",
    ]
    output = "\n".join(lines).rstrip() + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output, encoding="utf-8", newline="\n")
        print(args.out)
    else:
        print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
