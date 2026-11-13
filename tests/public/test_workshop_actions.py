"""Workshop action graphs: synthetic graphs in the shapes the game data uses, run by the script runtime."""

import unittest

from ow174.game.script import expr, runtime
from ow174.game.script.expr import ENTITY, INSTANCE, Entity
from ow174.workshop import actions
from ow174.workshop.actions import Flow
from tests.script_fixtures import graph, node, plug, setter

OWNER = 0x80000101
OTHER = 0x80000202
TARGET = 40  # an instance variable holding the entity a graph writes to


def element(index):
    """Element `index` of the action's parameter list."""
    return {
        "$": "STU_919FD47C",
        "m_expression": {
            "m_opcodes": [8, 0, 6, 0, 17, 0],
            "m_dynamicVars": [variable(actions.PARAMETERS)],
            "m_D99EF254": [index],
        },
    }


def number(value):
    return {"$": "STUConfigVarFloat" if isinstance(value, float) else "STUConfigVarInt", "m_value": value}


def parameter(index, low=None, high=None, entity=None):
    return {
        "$": actions.PARAMETER,
        "m_35547D6E": element(index),
        "m_entity": entity,
        "m_FDCA1FD0": None if low is None else number(low),
        "m_68CFF844": None if high is None else number(high),
    }


def variable(identifier, scope=INSTANCE):
    return {"$": "STUConfigVarDynamic", "m_identifier": identifier, "m_60DB8F99": scope}


def workshop_variable_named_by(index):
    """`#TARGET.workshop[parameters[index]]`, the out var of the Set Player Variable shape."""
    return {
        "$": "STU_919FD47C",
        "m_expression": {
            "m_opcodes": [8, 0, 8, 1, 6, 0, 17, expr.WORKSHOP_VARIABLE, 0],
            "m_dynamicVars": [variable(TARGET), variable(actions.PARAMETERS)],
            "m_D99EF254": [index],
        },
    }


def entry(position, target, path="m_inPlug"):
    return node(position, "STUStatescriptEntry", m_outPlug=plug((target, path)))


def done(position, *links):
    return node(position, actions.DONE, m_outPlug=plug(*links))


def action_graph(*nodes):
    """Entry at position 0, the given nodes after it."""
    return graph([entry(0, 1), *nodes], entries=[0])


class Host(actions.ActionHost, runtime.World):
    def __init__(self):
        super().__init__()
        self.events = []
        self.slots = {}
        self.scale = None

    def workshop_parameter(self, instance, parameter, entity):
        self.events.append(("parameter", parameter, entity))
        return parameter * self.scale if self.scale is not None else parameter

    def workshop_done(self, instance):
        self.events.append("done")

    def workshop_flow(self, instance, flow):
        self.events.append(flow)

    def entity_var_slot(self, entity, var, *, create=False):
        if entity != OTHER:
            return NotImplemented
        if (entity, var) not in self.slots and create:
            self.slots[entity, var] = runtime.Var((0, var))
        return self.slots.get((entity, var))


def run(model, parameters=(), *, world=None, strict=True, frames=1, target=OWNER):
    component = runtime.Component(OWNER, world=world, strict=strict)
    values = {(INSTANCE, actions.PARAMETERS): tuple(parameters), (INSTANCE, TARGET): Entity(target)}
    component.create(model, values=values)
    for frame in range(frames):
        component.run_frame(frame)
    return component


class ActionEndTests(unittest.TestCase):
    def test_last_node_reports_the_action_finished(self):
        host = Host()
        run(action_graph(done(1)), world=host)
        self.assertEqual(host.events, ["done"])

    def test_strict_execution_stops_without_an_action_host(self):
        with self.assertRaises(runtime.UnsupportedScriptError) as raised:
            run(action_graph(done(1)))
        self.assertEqual(raised.exception.diagnostic["feature"], "workshop action host")
        self.assertEqual(raised.exception.diagnostic["class"], actions.DONE)

    def test_without_a_host_the_runtime_keeps_its_policy_for_unmodelled_nodes(self):
        component = run(action_graph(done(1, (2, "m_inPlug")), setter(2, 5)), strict=False)
        self.assertEqual(component.instances[1].find_var(INSTANCE, 7).value(), 5)


class FlowTests(unittest.TestCase):
    def flow_of(self, cls, **fields):
        host = Host()
        model = action_graph(node(1, cls, m_outPlug=plug((2, "m_inPlug")), **fields), done(2))
        run(model, world=host)
        self.assertEqual(host.events[-1], "done")
        return host.events[0]

    def test_abort_and_loop_carry_their_two_condition_flags(self):
        cases = (
            (actions.ABORT, 0, 0, Flow("abort")),
            (actions.ABORT, 1, 0, Flow("abort", if_true=True)),
            (actions.ABORT, 0, 1, Flow("abort", if_false=True)),
            (actions.LOOP, 0, 0, Flow("loop")),
            (actions.LOOP, 1, 0, Flow("loop", if_true=True)),
        )
        for cls, if_true, if_false, expected in cases:
            self.assertEqual(self.flow_of(cls, m_F3733689=if_true, m_79252765=if_false), expected)

    def test_skip_count_is_the_limited_parameter(self):
        host = Host()
        model = action_graph(
            node(1, actions.SKIP, m_C337E584=parameter(0, 0, 99), m_outPlug=plug((2, "m_inPlug"))), done(2)
        )
        run(model, [250], world=host)
        self.assertEqual(host.events, [("parameter", 250, None), Flow("skip", count=99), "done"])


class ParameterTests(unittest.TestCase):
    def value_of(self, cfg, parameters, host=None):
        host = host or Host()
        component = runtime.Component(OWNER, world=host, strict=True)
        values = {(INSTANCE, actions.PARAMETERS): tuple(parameters), (INSTANCE, TARGET): Entity(OTHER)}
        return component.create(graph(), values=values, init=False).evaluate(cfg), host

    def test_reads_the_list_element_through_the_host(self):
        host = Host()
        host.scale = 2
        value, host = self.value_of(parameter(1), [10, 21], host)
        self.assertEqual(value, 42)
        self.assertEqual(host.events, [("parameter", 21, None)])

    def test_names_the_entity_the_parameter_is_read_for(self):
        _, host = self.value_of(parameter(0, entity=variable(TARGET)), [1])
        self.assertEqual(host.events, [("parameter", 1, OTHER)])

    def test_numbers_are_kept_within_the_limits_in_their_own_type(self):
        low, _ = self.value_of(parameter(0, 0.016, 100000), [0.001])
        self.assertEqual(low, expr.f32(0.016))
        high, _ = self.value_of(parameter(0, 0.016, 100000), [2.0e9])
        self.assertIs(type(high), float)
        self.assertEqual(high, 100000.0)
        whole, _ = self.value_of(parameter(0, 0, 99), [-7])
        self.assertIs(type(whole), int)
        self.assertEqual(whole, 0)
        inside, _ = self.value_of(parameter(0, -70, 70), [12.5])
        self.assertEqual(inside, 12.5)

    def test_other_values_and_absent_limits_pass_through(self):
        vector = expr.Vec3(0.0, 2000.0, 0.0)
        cases = ((True, parameter(0, 0, 1)), (vector, parameter(0, -1000, 1000)), (9.5, parameter(0)))
        for value, cfg in cases:
            result, _ = self.value_of(cfg, [value])
            self.assertEqual(result, value)
            self.assertIs(type(result), type(value))


class SetEntityVariableTests(unittest.TestCase):
    def assign(self, out_var, **fields):
        return action_graph(
            node(
                1, actions.SET_ENTITY_VARIABLE,
                m_entity=variable(TARGET), m_out_Var=out_var, m_value=parameter(1, -10000000, 10000000),
                m_outPlug=plug((2, "m_inPlug")), **fields,
            ),
            done(2),
        )

    def test_sets_the_workshop_variable_a_parameter_names(self):
        host = Host()
        component = run(self.assign(workshop_variable_named_by(0)), [7, 42.0], world=host)
        self.assertEqual(component.entity_var(expr.workshop_variable(7)).value(), 42.0)
        self.assertEqual(host.events, [("parameter", 42.0, None), "done"])

    def test_sets_another_entity_through_the_declared_slot(self):
        host = Host()
        run(self.assign(workshop_variable_named_by(0)), [3, 1.5], world=host, target=OTHER)
        self.assertEqual(host.slots[OTHER, expr.workshop_variable(3)].value(), 1.5)

    def test_another_entity_without_a_slot_service_is_unsupported(self):
        with self.assertRaises(runtime.UnsupportedScriptError) as raised:
            run(self.assign(workshop_variable_named_by(0)), [3, 1.5], world=Host(), target=0x80000303)
        self.assertEqual(raised.exception.diagnostic["feature"], "entity variable service")

    def test_plain_out_var_names_the_entity_variable_directly(self):
        component = run(self.assign(variable(321, ENTITY)), [0, 8], world=Host())
        self.assertEqual(component.entity_var(321).value(), 8)

    def test_index_and_key_are_not_guessed(self):
        with self.assertRaises(runtime.UnsupportedScriptError) as raised:
            run(self.assign(variable(321, ENTITY), m_index=number(0)), [0, 8], world=Host())
        self.assertEqual(raised.exception.diagnostic["feature"], "indexed or keyed entity variable")

    def test_absent_value_or_out_var_assigns_nothing_and_continues(self):
        host = Host()
        model = action_graph(
            node(1, actions.SET_ENTITY_VARIABLE, m_entity=variable(TARGET), m_outPlug=plug((2, "m_inPlug"))),
            done(2),
        )
        component = run(model, world=host)
        self.assertEqual(host.events, ["done"])
        self.assertEqual(component.vars, {})


if __name__ == "__main__":
    unittest.main()
