"""GraphWorld: the engine performs an action by running its graph in a scene, with synthetic graphs."""

import unittest

from ow174.game.script.expr import ENTITY, INSTANCE, Entity, Vec3
from ow174.workshop import actions
from ow174.workshop.engine import Action, Engine, Rule, Script, Unsupported, Value, number
from ow174.workshop.graph_world import GAME, GraphWorld, full_guid, to_script
from ow174.workshop.values import Hero, team
from ow174.workshop.world import SimpleWorld
from tests.script_fixtures import node, plug

OPTION = "000000004A29.01C"
SEEN, CHOSEN, AT = 501, 502, 503  # entity variables the synthetic actions write on the game entity


def variable(identifier, scope=INSTANCE):
    return {"$": "STUConfigVarDynamic", "m_identifier": identifier, "m_60DB8F99": scope}


def element(index):
    return {
        "$": "STU_919FD47C",
        "m_expression": {
            "m_opcodes": [8, 0, 6, 0, 17, 0],
            "m_dynamicVars": [variable(actions.PARAMETERS)],
            "m_D99EF254": [index],
        },
    }


def parameter(index):
    return {
        "$": actions.PARAMETER,
        "m_35547D6E": element(index),
        "m_entity": None,
        "m_FDCA1FD0": None,
        "m_68CFF844": None,
    }


def record(index, nodes, states=()):
    return {
        "index": index,
        "header": {},
        "fields": {},
        "items": len(nodes),
        "containers": {},
        "nodes": nodes,
        "unknown_nodes": [],
        "states": list(states),
        "entries": [0],
        "remote": [],
        "sync_vars": [],
    }


def setter(position, target, value, after):
    return node(
        position,
        "STUStatescriptActionSetVar",
        m_out_Var=variable(target, ENTITY),
        m_value=value,
        m_outPlug=plug((after, "m_inPlug")),
    )


BUNDLE = {
    "workshop": {
        "actions": [
            {"name": "Record", "graph": 0x10},
            {"name": "Hold", "graph": 0x11},
            {"name": "If", "graph": None},
        ]
    },
    "graphs": [
        # Record(value, option): copy both parameters to entity variables, then finish.
        record(
            0x10,
            [
                node(0, "STUStatescriptEntry", m_outPlug=plug((1, "m_inPlug"))),
                setter(1, SEEN, parameter(0), 2),
                setter(2, CHOSEN, element(1), 3),
                node(3, actions.DONE, m_outPlug=plug()),
            ],
        ),
        # Hold(seconds): wait for the parameter, then record the time and finish.
        record(
            0x11,
            [
                node(0, "STUStatescriptEntry", m_outPlug=plug((1, "m_beginPlug"))),
                node(
                    1,
                    "STUStatescriptStateWait",
                    state=0,
                    m_timeout=parameter(0),
                    m_onFinishedPlug=plug((2, "m_inPlug")),
                ),
                setter(2, AT, {"$": "STUConfigVarBool", "m_value": 1}, 3),
                node(3, actions.DONE, m_outPlug=plug()),
            ],
            states=[1],
        ),
    ],
}
CATALOG = {
    "Actions": [
        {
            "DisplayName": "Record",
            "Parameters": [
                {"InferredType": "GenericInput", "InputType": "Generic"},
                {"InferredType": "Dropdown", "DropdownId": "D"},
            ],
        },
        {"DisplayName": "Hold", "Parameters": [{"InferredType": "GenericInput", "InputType": "Float"}]},
    ],
    "Dropdowns": [{"Id": "D", "Options": [{"DisplayName": "Add", "VirtualId": OPTION}]}],
}


def run(actions_list, frames=1):
    players = SimpleWorld()
    players.add_player(0x80000101, team="Team 1")
    world = GraphWorld(BUNDLE, CATALOG, players)
    engine = Engine(Script(rules=(Rule("r", actions=tuple(actions_list)),)), world)
    engine.run(frames)
    return engine, world


class GraphWorldTests(unittest.TestCase):
    def test_parameters_reach_the_graph_and_the_rule_continues_when_it_finishes(self):
        engine, world = run(
            [
                Action("Record", (Value("Add", (number(2), number(3))), "Add")),
                Action("Set Global Variable", ("A", number(1))),
            ]
        )
        game = world.components[GAME]
        self.assertEqual(game.entity_var(SEEN).value(), 5.0)
        self.assertEqual(game.entity_var(CHOSEN).value().guid, full_guid(OPTION))
        self.assertEqual(engine.globals[0], 1.0)

    def test_a_graph_that_waits_holds_the_rule(self):
        engine, world = run(
            [Action("Hold", (number(0.05),)), Action("Set Global Variable", ("A", number(1)))]
        )
        self.assertEqual(engine.globals[0], 0)
        engine.run(4)
        self.assertTrue(world.components[GAME].entity_var(AT).value())
        self.assertEqual(engine.globals[0], 1.0)

    def test_players_get_components_and_other_actions_go_to_the_players_world(self):
        _, world = run([Action("Big Message", (Value("All Players", (team("All Teams"),)), "hi"))])
        self.assertIn(0x80000101, world.components)
        self.assertEqual(world.players_world.messages, [("big", (Entity(0x80000101),), "hi")])

    def test_values_without_a_statescript_form_and_unknown_options_are_unsupported(self):
        self.assertEqual(to_script((1, Vec3(1, 2, 3), True, None)), (1.0, Vec3(1.0, 2.0, 3.0), True, None))
        with self.assertRaises(Unsupported):
            to_script(Hero("Ana"))
        with self.assertRaises(Unsupported):
            run([Action("Record", (number(1), "Multiply"))])


if __name__ == "__main__":
    unittest.main()
