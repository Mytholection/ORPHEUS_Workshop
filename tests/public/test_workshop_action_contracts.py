"""The shared Workshop action graph contract, checked on the production runtime and handlers."""

import json
import os
import unittest
from pathlib import Path

from ow174.game.script import expr, runtime
from ow174.game.script.graph import Graph
from ow174.workshop import actions

FIXTURES = Path(
    os.environ.get("ORPHEUS_BEHAVIOR_FIXTURES")
    or Path(__file__).resolve().parents[2] / "fixtures/behavior"
)
KINDS = {"boolean": bool, "integer": int, "float": float}
EMPTY_GRAPH = {
    "index": 1, "header": {}, "fields": {}, "items": 0, "containers": {}, "nodes": [],
    "unknown_nodes": [], "states": [], "entries": [], "remote": [], "sync_vars": [],
}


def fixture_value(item):
    if item["kind"] == "null":
        return None
    if item["kind"] == "entity":
        return expr.Entity(item["value"])
    return KINDS[item["kind"]](item["value"])


class RecordingHost(actions.ActionHost, runtime.World):
    def __init__(self):
        super().__init__()
        self.events = []

    def workshop_done(self, instance):
        self.events.append({"event": "done"})

    def workshop_flow(self, instance, flow):
        self.events.append({
            "event": "flow", "kind": flow.kind, "if_true": flow.if_true, "if_false": flow.if_false,
            "count": flow.count,
        })


class WorkshopActionContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        text = (FIXTURES / "workshop-action-graphs-v1.json").read_text(encoding="utf-8")
        cls.contract = json.loads(text)

    def assert_value(self, value, expected):
        if expected["kind"] == "null":
            self.assertEqual(set(expected), {"kind"})
            self.assertIsNone(value)
        elif expected["kind"] == "entity":
            self.assertIsInstance(value, expr.Entity)
            self.assertEqual(value.id, expected["value"])
        else:
            self.assertIs(type(value), KINDS[expected["kind"]])
            self.assertEqual(value, expected["value"])

    def test_contract_header_and_case_identifiers(self):
        contract = self.contract
        self.assertEqual(contract["schema_version"], 1)
        self.assertEqual(contract["case_id"], "workshop-action-graphs.synthetic.v1")
        self.assertEqual(contract["target_build"], 104319)
        self.assertEqual(contract["evidence"], "synthetic-reference")
        self.assertEqual(contract["client_acceptance"], "pending")
        identifiers = [case["id"] for case in contract["input"]["cases"]]
        self.assertTrue(identifiers, "the contract must exercise at least one case")
        self.assertEqual(len(identifiers), len(set(identifiers)), "duplicate case IDs")
        self.assertEqual(set(contract["expected"]), set(identifiers))
        self.assertEqual({case["kind"] for case in contract["input"]["cases"]}, {"expression", "action"})

    def test_workshop_variable_expressions(self):
        for case in self.contract["input"]["cases"]:
            if case["kind"] != "expression":
                continue
            with self.subTest(case=case["id"]):
                context = case["context"]
                expected = self.contract["expected"][case["id"]]
                component = runtime.Component(context["owner"], strict=True)
                values = {
                    (expr.INSTANCE, int(key)): fixture_value(item)
                    for key, item in context["instance_variables"].items()
                }
                instance = component.create(Graph(EMPTY_GRAPH), values=values, init=False)
                for key, item in context["entity_variables"].items():
                    component.set(int(key), fixture_value(item))
                if case["as"] == "destination":
                    self.assertEqual(set(expected), {"variable"})
                    found = expr.workshop_lvalue(case["config"], instance.context())
                    self.assertEqual(found, expected["variable"])
                else:
                    self.assertEqual(case["as"], "value")
                    self.assertEqual(set(expected), {"value"})
                    self.assert_value(instance.evaluate(case["config"]), expected["value"])
                self.assertIsNone(component.fault)

    def test_action_graphs(self):
        for case in self.contract["input"]["cases"]:
            if case["kind"] != "action":
                continue
            with self.subTest(case=case["id"]):
                context = case["context"]
                expected = self.contract["expected"][case["id"]]
                world = RecordingHost() if context["host"] else runtime.World()
                component = runtime.Component(context["owner"], world=world, strict=True)
                values = {
                    (expr.INSTANCE, int(key)): fixture_value(item)
                    for key, item in context["instance_variables"].items()
                }
                parameters = tuple(fixture_value(item) for item in context["parameters"])
                values[(expr.INSTANCE, actions.PARAMETERS)] = parameters

                def play(component=component, values=values, graph=case["graph"], frames=context["frames"]):
                    component.create(Graph(graph), values=values)
                    for frame in range(frames):
                        component.run_frame(frame)

                if "error" in expected:
                    self.assertEqual(set(expected), {"error"})
                    with self.assertRaises(runtime.UnsupportedScriptError) as raised:
                        play()
                    diagnostic = raised.exception.diagnostic
                    self.assertEqual(diagnostic["feature"], expected["error"]["feature"])
                    self.assertEqual(diagnostic["class"], expected["error"]["class"])
                    self.assertEqual(diagnostic["entity"], context["owner"])
                    self.assertIs(component.fault, raised.exception)
                else:
                    self.assertEqual(set(expected), {"events", "entity_variables"})
                    play()
                    self.assertEqual(world.events, expected["events"])
                    written = {str(key): var for key, var in component.vars.items()}
                    self.assertEqual(set(written), set(expected["entity_variables"]))
                    for key, item in expected["entity_variables"].items():
                        self.assert_value(written[key].value(), item)
                    self.assertIsNone(component.fault)


if __name__ == "__main__":
    unittest.main()
