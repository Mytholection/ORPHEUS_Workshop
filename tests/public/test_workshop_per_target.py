"""The per-target state: one child of the action's graph per target, on the target's own component."""

import unittest

from ow174.game.script import runtime, scene
from ow174.game.script.expr import ENTITY, INSTANCE, Entity
from ow174.workshop import actions
from tests.script_fixtures import graph, node, plug

GAME = runtime.GAME_MODE_ENTITY
ONE, TWO = 0x80000101, 0x80000202
TARGETS = 7566  # the action graphs keep the target list in this instance variable
MARK = 20763  # an entity variable each branch sets on its target


class Scene(actions.ActionHost, scene.SceneWorld):
    def __init__(self):
        super().__init__()
        self.finished = []

    def workshop_done(self, instance):
        self.finished.append(instance.id)


def variable(identifier, scope=INSTANCE):
    return {"$": "STUConfigVarDynamic", "m_identifier": identifier, "m_60DB8F99": scope}


def per_target_graph():
    """Entry -> per-target state over #TARGETS; its branch sets MARK on the target and copies the parent's
    variable 9 (opcode 10, one level up) into the target's entity variable 10."""
    parent_nine = {
        "$": "STU_919FD47C",
        "m_expression": {"m_opcodes": [10, 1, 0, 0], "m_dynamicVars": [variable(9)]},
    }
    parent_entity = {"$": "STU_919FD47C", "m_expression": {"m_opcodes": [21, 1, 0]}}
    return graph(
        [
            node(0, "STUStatescriptEntry", m_outPlug=plug((1, "m_beginPlug"))),
            node(
                1, actions.PER_TARGET, state=0, m_targets=variable(TARGETS), m_C41A9BE2=plug((2, "m_inPlug"))
            ),
            node(
                2,
                "STUStatescriptActionSetVar",
                m_out_Var=variable(MARK, ENTITY),
                m_value={"$": "STUConfigVarBool", "m_value": 1},
                m_outPlug=plug((3, "m_inPlug")),
            ),
            node(
                3,
                "STUStatescriptActionSetVar",
                m_out_Var=variable(10, ENTITY),
                m_value=parent_nine,
                m_outPlug=plug((4, "m_inPlug")),
            ),
            node(4, "STUStatescriptActionSetVar", m_out_Var=variable(11, ENTITY), m_value=parent_entity),
        ],
        entries=[0],
    )


class PerTargetTests(unittest.TestCase):
    def setUp(self):
        self.world = Scene()
        self.components = {}
        for entity in (GAME, ONE, TWO):
            self.world.bind(entity)
            component = runtime.Component(entity, world=self.world, strict=True)
            self.world.bind_script_component(entity, component)
            self.components[entity] = component

    def start(self, targets):
        game = self.components[GAME]
        values = {(INSTANCE, TARGETS): targets, (INSTANCE, 9): 42}
        instance = game.create(per_target_graph(), values=values)
        game.run_frame(0)
        return instance

    def test_each_target_runs_the_branch_on_its_own_component(self):
        self.start((Entity(ONE), Entity(TWO)))
        for entity in (ONE, TWO):
            component = self.components[entity]
            self.assertTrue(component.entity_var(MARK).value())
            self.assertEqual(component.entity_var(10).value(), 42)  # read from the parent instance
            self.assertEqual(component.entity_var(11).value(), Entity(GAME))  # the parent's entity
        self.assertIsNone(self.components[GAME].entity_var(MARK, create=False))

    def test_a_single_target_and_repeated_or_invalid_entries(self):
        self.start((Entity(ONE), Entity(ONE), None, 0))
        self.assertTrue(self.components[ONE].entity_var(MARK).value())
        self.assertEqual(len(self.components[ONE].instances), 1)

    def test_children_follow_the_target_list_and_end_with_the_state(self):
        instance = self.start((Entity(ONE),))
        state = instance.state(0)
        self.assertEqual([entity for entity, _ in state.children], [ONE])
        instance.write((INSTANCE, TARGETS), (Entity(TWO),))
        self.components[GAME].run_frame(1)
        self.assertEqual([entity for entity, _ in state.children], [TWO])
        self.assertEqual(len(self.components[ONE].instances), 0)
        self.components[GAME].destroy(instance)
        self.assertEqual(len(self.components[TWO].instances), 0)

    def test_a_target_without_a_component_stops_strict_execution(self):
        with self.assertRaises(runtime.UnsupportedScriptError) as raised:
            self.start((Entity(0x80000303),))
        self.assertEqual(raised.exception.diagnostic["feature"], "per-target component")

    def test_parent_entity_walks_up_only_as_far_as_the_chain_goes(self):
        component = self.components[ONE]
        lone = component.create(graph(), init=False)
        self.assertEqual(lone.context().proxy_entity(2), Entity(ONE))


if __name__ == "__main__":
    unittest.main()
