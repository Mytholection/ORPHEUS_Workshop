"""The Workshop variable opcode: an entity's 128 Workshop variables, read and named as a destination."""

import unittest

from ow174.game.script import expr, runtime
from ow174.game.script.expr import ENTITY, INSTANCE, Entity
from tests.script_fixtures import graph

OWNER = 0x80000101
OTHER = 0x80000202
HOLDER = 50  # an instance variable holding the entity whose Workshop variable is read


def variable_of(index, *, holder=HOLDER):
    """`#holder.workshop[index]`: push the entity, push the index, WORKSHOP_VARIABLE, END."""
    return {
        "$": "STU_919FD47C",
        "m_expression": {
            "m_opcodes": [8, 0, 6, 0, expr.WORKSHOP_VARIABLE, 0],
            "m_dynamicVars": [{"$": "STUConfigVarDynamic", "m_identifier": holder, "m_60DB8F99": 0}],
            "m_D99EF254": [index],
        },
    }


class ForeignWorld(runtime.World):
    def __init__(self, members):
        super().__init__()
        self.members = members

    def entity_var(self, entity, var):
        return self.members.get((entity, var))


def instance_of(entity=OWNER, world=None):
    instance = runtime.Component(OWNER, world=world).create(graph(), init=False)
    instance.write((INSTANCE, HOLDER), Entity(entity))
    return instance


class WorkshopVariableTests(unittest.TestCase):
    def test_index_maps_to_the_reserved_entity_variable_identifiers(self):
        self.assertEqual(expr.workshop_variable(0), 0xFF7F)
        self.assertEqual(expr.workshop_variable(127), 0xFFFE)
        self.assertEqual(expr.workshop_variable(-3), 0xFF7F)
        self.assertEqual(expr.workshop_variable(128), 0xFFFE)

    def test_reads_the_variable_of_the_entity_below_the_index(self):
        instance = instance_of()
        instance.component.set(expr.workshop_variable(3), 42)
        self.assertEqual(instance.evaluate(variable_of(3)), 42)

    def test_index_is_converted_to_int_and_limited_to_the_128_slots(self):
        instance = instance_of()
        instance.component.set(expr.workshop_variable(0), "first")
        instance.component.set(expr.workshop_variable(3), "fourth")
        instance.component.set(expr.workshop_variable(127), "last")
        self.assertEqual(instance.evaluate(variable_of(-4)), "first")
        self.assertEqual(instance.evaluate(variable_of(2.6)), "fourth")
        self.assertEqual(instance.evaluate(variable_of(900)), "last")

    def test_unset_variable_and_invalid_entity_give_int_zero(self):
        instance = instance_of()
        unset = instance.evaluate(variable_of(9))
        self.assertIs(type(unset), int)
        self.assertEqual(unset, 0)
        instance.write((INSTANCE, HOLDER), None)
        nobody = instance.evaluate(variable_of(9))
        self.assertIs(type(nobody), int)
        self.assertEqual(nobody, 0)

    def test_reads_another_entity_through_the_world(self):
        world = ForeignWorld({(OTHER, expr.workshop_variable(5)): 7.5})
        instance = instance_of(OTHER, world)
        self.assertEqual(instance.evaluate(variable_of(5)), 7.5)
        self.assertEqual(instance.evaluate(variable_of(6)), 0)

    def test_expression_text_names_the_variable(self):
        self.assertEqual(expr.source(variable_of(3)), "#50.workshop[3.0]")


class WorkshopDestinationTests(unittest.TestCase):
    def setUp(self):
        self.instance = instance_of()
        self.context = self.instance.context()

    def test_destination_is_the_identifier_of_the_evaluated_index(self):
        self.assertEqual(expr.workshop_lvalue(variable_of(5), self.context), 0xFF7F + 5)
        self.assertEqual(expr.workshop_lvalue(variable_of(400), self.context), 0xFFFE)

    def test_index_can_come_from_a_list_element(self):
        self.instance.write((INSTANCE, 60), (2.0, 11.0))
        cfg = {
            "$": "STU_919FD47C",
            "m_expression": {
                "m_opcodes": [8, 0, 8, 1, 6, 0, 17, expr.WORKSHOP_VARIABLE, 0],
                "m_dynamicVars": [
                    {"$": "STUConfigVarDynamic", "m_identifier": HOLDER, "m_60DB8F99": 0},
                    {"$": "STUConfigVarDynamic", "m_identifier": 60, "m_60DB8F99": 0},
                ],
                "m_D99EF254": [1],
            },
        }
        self.assertEqual(expr.workshop_lvalue(cfg, self.context), 0xFF7F + 11)

    def test_other_out_vars_are_not_workshop_destinations(self):
        plain = {"$": "STUConfigVarDynamic", "m_identifier": 7, "m_60DB8F99": 1}
        push_only = {"$": "STU_919FD47C", "m_expression": {"m_opcodes": [8, 0, 0], "m_dynamicVars": [plain]}}
        operand = {
            "$": "STU_919FD47C",
            "m_expression": {"m_opcodes": [6, expr.WORKSHOP_VARIABLE, 0], "m_D99EF254": [0.0] * 73},
        }
        for cfg in (None, plain, push_only, operand):
            self.assertIsNone(expr.workshop_lvalue(cfg, self.context))
        self.assertEqual(expr.lvalue(plain), (ENTITY, 7))


if __name__ == "__main__":
    unittest.main()
