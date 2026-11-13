#!/usr/bin/env python3
"""Make a local bundle of the Workshop action graphs of Overwatch 1.74.

In build 104319 a Workshop action is a statescript graph in the game data. This reads two DataTool
outputs of a local install (OWLib 7afe5f52, the revision data/README.md names):

    DataTool <game> list-workshop --json --out=<catalog.json>
    DataTool <game> extract-stu-type <dump> 01B --xml

and keeps the graph of every catalog action and of the condition entry, plus every graph those name.

    py -X utf8 tools/extract_workshop_graphs.py --catalog <catalog.json> --xml <dump>/01B \
        --owlib <OWLib checkout> --output <bundle outside the repository>

The bundle has the format ow174/game/script/graph.py reads ("graphs", "missing", empty "bodies") and one
more section, "workshop":

- "actions": the catalog's actions in catalog order: {"name", "graph"}; "graph" is the 01B index, or null
  for an action without one (If, While, For, Call Subroutine and the like, which a rule engine handles).
- "conditions": the same for the catalog's condition entry.

The bundle is game data: keep it in local storage. tests/runtime/test_workshop_action_graphs.py runs
the graphs when ORPHEUS_WORKSHOP_GRAPHS names it.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.extract_game_graphs import EnumTables, GraphXml, guid_index, write_bundle

ROOT = Path(__file__).resolve().parents[1]


def catalog_entries(catalog: dict) -> tuple[list[dict], list[dict]]:
    """The catalog's actions and its condition entries as {"name", "graph"}, in catalog order."""

    def entry(item: dict) -> dict:
        guid = item.get("GraphId")
        return {"name": item.get("DisplayName"), "graph": guid_index(guid) if guid else None}

    actions = [entry(item) for item in catalog.get("Actions") or []]
    conditions = [entry(item) for item in catalog.get("Unknown") or []]
    return actions, conditions


def collect(catalog: dict, xml_dir: Path, enums: EnumTables) -> tuple[dict, dict[int, list[str]]]:
    """The bundle and, per graph, the links the extractor could not resolve."""
    actions, conditions = catalog_entries(catalog)
    roots = sorted({item["graph"] for item in (*actions, *conditions) if item["graph"] is not None})
    records, missing, problems = {}, set(), {}
    pending = list(reversed(roots))
    while pending:
        index = pending.pop()
        if index in records or index in missing:
            continue
        path = xml_dir / f"{index:012X}.01B.xml"
        if not path.is_file():
            missing.add(index)
            continue
        xml = GraphXml(path, enums)
        records[index] = xml.record(index)
        if xml.problems:
            problems[index] = list(xml.problems)
        pending.extend(sorted(xml.graph_refs() - set(records) - missing, reverse=True))
    bundle = {
        "version": 1,
        "roots": {"bodies": [], "graphs": roots},
        "bodies": {},
        "missing": sorted(missing),
        "workshop": {"actions": actions, "conditions": conditions},
        "graphs": [records[index] for index in sorted(records)],
    }
    return bundle, problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--catalog", type=Path, required=True, help="DataTool list-workshop JSON")
    parser.add_argument("--xml", type=Path, required=True, help="folder of <index>.01B.xml files")
    parser.add_argument("--owlib", type=Path, required=True, help="the OWLib checkout that made the dump")
    parser.add_argument("--output", type=Path, required=True, help="destination, outside the repository")
    args = parser.parse_args(argv)
    if args.output.resolve().is_relative_to(ROOT):
        parser.error("--output must be outside the repository: the bundle is game data")
    try:
        catalog = json.loads(args.catalog.read_text(encoding="utf-8-sig"))
        if not isinstance(catalog, dict) or not isinstance(catalog.get("Actions"), list):
            raise ValueError("the catalog has no Actions list")
        bundle, problems = collect(catalog, args.xml, EnumTables(args.owlib / "TankLib" / "STU" / "Types"))
    except (OSError, ValueError) as error:
        parser.error(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_bundle(args.output, bundle)
    actions = bundle["workshop"]["actions"]
    with_graph = sum(item["graph"] is not None for item in actions)
    nodes = sum(len(graph["nodes"]) for graph in bundle["graphs"])
    print(f"{len(actions)} actions, {with_graph} with a graph; {len(bundle['graphs'])} graphs, {nodes} nodes "
          f"-> {args.output}")
    if bundle["missing"]:
        print("named but not in the dump: " + " ".join(f"{index:04X}" for index in bundle["missing"]))
    for index, items in sorted(problems.items()):
        print(f"  {index:04X}: {len(items)} unresolved links, first: {items[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
