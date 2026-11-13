"""The client's own Workshop action graphs, run by the script runtime with ow174.workshop.actions.

tools/extract_workshop_graphs.py writes the bundle from a local 104319 install. Name its path in
ORPHEUS_WORKSHOP_GRAPHS; without it these checks are skipped. The bundle is game data and stays local.
"""

import gzip
import json
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ow174.game.script import expr, runtime
from ow174.game.script.expr import INSTANCE, Entity
from ow174.game.script.graph import Graph
from ow174.workshop import actions
from ow174.workshop.actions import Flow

BUNDLE = os.environ.get("ORPHEUS_WORKSHOP_GRAPHS")
GAME = 0x80000101  # the entity the graphs run on here; the "game entity" config var names it too
GAME_ENTITY = "STU_A3DEF368"


class Host(actions.ActionHost, runtime.World):
    def __init__(self):
        super().__init__()
        self.events = []

    def workshop_done(self, instance):
        self.events.append("done")

    def workshop_flow(self, instance, flow):
        self.events.append(flow)

    def native(self, cfg, instance):
        if cfg.get("$") == GAME_ENTITY:
            return Entity(GAME)
        return super().native(cfg, instance)


@unittest.skipUnless(BUNDLE, "requires the locally extracted 104319 Workshop action graphs")
class WorkshopActionGraphTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data = json.loads(gzip.decompress(Path(BUNDLE).read_bytes()))
        cls.records = {record["index"]: record for record in data["graphs"]}
        cls.actions = {item["name"]: item["graph"] for item in data["workshop"]["actions"]}

    def run_action(self, name, parameters, frames=1):
        host = Host()
        component = runtime.Component(GAME, world=host, strict=True)
        model = Graph(self.records[self.actions[name]])
        component.create(model, values={(INSTANCE, actions.PARAMETERS): tuple(parameters)})
        done_frame = None
        for frame in range(frames):
            component.run_frame(frame)
            if done_frame is None and "done" in host.events:
                done_frame = frame
        return component, host, done_frame

    def test_every_action_with_a_graph_ends_in_the_done_node(self):
        with_graph = [graph for graph in self.actions.values() if graph is not None]
        self.assertEqual(len(with_graph), 211)
        self.assertEqual(len(self.actions) - len(with_graph), 11)
        for name, index in self.actions.items():
            if index is not None:
                classes = {node["class"] for node in self.records[index]["nodes"]}
                self.assertIn(actions.DONE, classes, name)

    def test_set_global_variable_assigns_the_named_workshop_variable(self):
        component, host, done_frame = self.run_action("Set Global Variable", [7, 42.0])
        self.assertEqual(component.entity_var(expr.workshop_variable(7)).value(), 42.0)
        self.assertEqual(host.events, ["done"])
        self.assertEqual(done_frame, 0)

    def test_set_global_variable_limits_the_value(self):
        component, _, _ = self.run_action("Set Global Variable", [0, 2.0e9])
        self.assertEqual(component.entity_var(expr.workshop_variable(0)).value(), 10000000.0)

    def test_abort_variants_raise_their_flags_and_finish(self):
        cases = {
            "Abort": Flow("abort"),
            "Abort If Condition Is True": Flow("abort", if_true=True),
            "Abort If Condition Is False": Flow("abort", if_false=True),
            "Loop": Flow("loop"),
            "Loop If Condition Is True": Flow("loop", if_true=True),
            "Loop If Condition Is False": Flow("loop", if_false=True),
        }
        for name, expected in cases.items():
            _, host, _ = self.run_action(name, [])
            self.assertEqual(host.events, [expected, "done"], name)

    def test_abort_if_follows_its_condition_parameter(self):
        _, host, _ = self.run_action("Abort If", [True])
        self.assertEqual(host.events, [Flow("abort"), "done"])
        _, host, _ = self.run_action("Abort If", [False])
        self.assertEqual(host.events, ["done"])

    def test_skip_passes_the_limited_count(self):
        _, host, _ = self.run_action("Skip", [3])
        self.assertEqual(host.events, [Flow("skip", count=3), "done"])
        _, host, _ = self.run_action("Skip", [500])
        self.assertEqual(host.events, [Flow("skip", count=99), "done"])

    def test_wait_finishes_in_the_frame_its_time_elapses(self):
        _, host, done_frame = self.run_action("Wait", [0.25, 0], frames=20)
        self.assertEqual(host.events, ["done"])
        self.assertEqual(done_frame, 15)  # 250 ms falls in the frame that covers 240..255 ms

    def test_wait_never_runs_shorter_than_the_graph_minimum(self):
        _, _, done_frame = self.run_action("Wait", [0.0, 0], frames=4)
        self.assertEqual(done_frame, 1)  # the 0.016 s minimum ends in the second 16 ms frame


if __name__ == "__main__":
    unittest.main()
