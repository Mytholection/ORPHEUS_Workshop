"""Workshop values: numbers, vectors, logic, arrays, text and players, evaluated in a running rule."""

import math
import unittest

from ow174.game.script.expr import Vec3
from ow174.workshop import values
from ow174.workshop.engine import Engine, Event, Execution, Rule, Script, Value, number
from ow174.workshop.values import ALL_TEAMS, TEAM_2, Hero, Team, team, text
from ow174.workshop.world import SimpleWorld


def V(name, *args):
    return Value(name, args)


def vec(x, y, z):
    return V("Vector", number(x), number(y), number(z))


def arr(*items):
    return V("Array", *(number(item) if isinstance(item, (int, float)) else item for item in items))


class Evaluator:
    def __init__(self, world=None, player=None):
        self.world = world or SimpleWorld()
        self.engine = Engine(Script(), self.world)
        self.execution = Execution(Rule("probe"), Event("Ongoing - Global", player))
        self.ctx = values.Context(self.engine, self.execution)

    def __call__(self, value):
        return self.ctx.eval(value)


class NumberTests(unittest.TestCase):
    def setUp(self):
        self.eval = Evaluator()

    def test_arithmetic_and_its_zero_rules(self):
        cases = {
            V("Add", number(2), number(3)): 5.0,
            V("Subtract", number(2), number(3)): -1.0,
            V("Multiply", number(2), number(3)): 6.0,
            V("Divide", number(1), number(0)): 0.0,
            V("Modulo", number(-7), number(3)): -1.0,
            V("Modulo", number(7), number(0)): 0.0,
            V("Raise To Power", number(-8), number(0.5)): 0.0,
            V("Min", number(2), number(-3)): -3.0,
            V("Absolute Value", number(-4)): 4.0,
            V("Square Root", number(-4)): 0.0,
            V(" ", number(2), "Raise To Power", number(3)): 8.0,
        }
        for value, expected in cases.items():
            with self.subTest(value=value.name):
                self.assertEqual(self.eval(value), expected)

    def test_rounding_modes(self):
        for x, mode, expected in (
            (2.5, "To Nearest", 3.0),
            (-2.5, "To Nearest", -3.0),
            (2.1, "Up", 3.0),
            (-2.1, "Down", -3.0),
            (2.4, "To Nearest", 2.0),
        ):
            self.assertEqual(self.eval(V("Round To Integer", number(x), mode)), expected)

    def test_trigonometry_in_degrees_and_radians(self):
        self.assertAlmostEqual(self.eval(V("Sine From Degrees", number(30))), 0.5)
        self.assertAlmostEqual(self.eval(V("Cosine From Radians", number(math.pi))), -1.0)
        self.assertAlmostEqual(self.eval(V("Arcsine In Degrees", number(2))), 90.0)
        self.assertAlmostEqual(self.eval(V("Arctangent In Degrees", number(1), number(-1))), 135.0)
        self.assertAlmostEqual(self.eval(V("Angle Difference", number(350), number(10))), 20.0)
        self.assertAlmostEqual(self.eval(V("Angle Difference", number(10), number(350))), -20.0)

    def test_random_values_use_the_worlds_seeded_generator(self):
        first = [Evaluator()(V("Random Integer", number(1), number(6))) for _ in range(3)]
        again = [Evaluator()(V("Random Integer", number(1), number(6))) for _ in range(3)]
        self.assertEqual(first, again)
        self.assertTrue(all(1 <= item <= 6 for item in first))


class VectorTests(unittest.TestCase):
    def setUp(self):
        self.eval = Evaluator()

    def test_directions_follow_the_workshop_axes(self):
        self.assertEqual(self.eval(V("Left")), Vec3(1.0, 0.0, 0.0))
        self.assertEqual(self.eval(V("Forward")), Vec3(0.0, 0.0, 1.0))
        down = self.eval(V("Direction From Angles", number(0), number(90)))
        self.assertAlmostEqual(down.y, -1.0)
        left = self.eval(V("Direction From Angles", number(90), number(0)))
        self.assertAlmostEqual(left.x, 1.0)
        self.assertAlmostEqual(self.eval(V("Horizontal Angle From Direction", V("Left"))), 90.0)
        self.assertAlmostEqual(self.eval(V("Vertical Angle From Direction", V("Up"))), -90.0)

    def test_vector_operations(self):
        a, b = vec(1, 2, 2), vec(4, 6, 2)
        self.assertEqual(self.eval(V("Add", a, b)), Vec3(5.0, 8.0, 4.0))
        self.assertEqual(self.eval(V("Multiply", a, number(2))), Vec3(2.0, 4.0, 4.0))
        self.assertEqual(self.eval(V("Divide", a, vec(0, 2, 4))), Vec3(0.0, 1.0, 0.5))
        self.assertEqual(self.eval(V("Distance Between", a, b)), 5.0)
        self.assertEqual(self.eval(V("Magnitude Of", a)), 3.0)
        self.assertEqual(self.eval(V("Vector Towards", a, b)), Vec3(3.0, 4.0, 0.0))
        self.assertEqual(self.eval(V("Direction Towards", a, b)), Vec3(0.6, 0.8, 0.0))
        self.assertEqual(self.eval(V("Dot Product", a, b)), 20.0)
        self.assertEqual(self.eval(V("Cross Product", V("Left"), V("Up"))), Vec3(0.0, 0.0, 1.0))
        self.assertAlmostEqual(self.eval(V("Angle Between Vectors", V("Up"), V("Left"))), 90.0)
        self.assertEqual(self.eval(V("Normalize", vec(0, 0, 0))), Vec3(0.0, 0.0, 0.0))
        self.assertEqual(self.eval(V("Y Component Of", a)), 2.0)


class LogicTests(unittest.TestCase):
    def setUp(self):
        self.eval = Evaluator()

    def test_comparisons_use_the_value_models_tolerance(self):
        self.assertTrue(self.eval(V("Compare", number(0.1 + 0.2), "==", number(0.3))))
        self.assertTrue(self.eval(V("Compare", V("Null"), "==", number(0))))
        self.assertTrue(self.eval(V("Compare", number(1), "<=", number(1))))
        self.assertFalse(self.eval(V("Compare", number(1), "<", number(1))))
        self.assertTrue(self.eval(V("Compare", arr(1, 2), "==", arr(1, 2))))
        self.assertFalse(self.eval(V("Compare", V("Hero", "Ana"), "==", V("Hero", "Mercy"))))
        self.assertTrue(self.eval(V("Compare", V("True"), "==", number(1))))

    def test_and_or_not_and_if_then_else(self):
        self.assertTrue(self.eval(V("And", number(1), V("True"))))
        self.assertFalse(self.eval(V("Or", V("Null"), V("Empty Array"))))
        self.assertTrue(self.eval(V("Not", vec(0, 0, 0))))
        self.assertEqual(self.eval(V("If-Then-Else", V("False"), number(1), number(2))), 2.0)


class ArrayTests(unittest.TestCase):
    def setUp(self):
        self.eval = Evaluator()

    def test_array_access_and_change(self):
        items = arr(3, 1, 2)
        self.assertEqual(self.eval(V("Count Of", items)), 3.0)
        self.assertEqual(self.eval(V("Count Of", number(5))), 0.0)
        self.assertEqual(self.eval(V("Value In Array", items, number(9))), 0)
        self.assertEqual(self.eval(V("First Of", V("Empty Array"))), None)
        self.assertEqual(self.eval(V("Last Of", items)), 2.0)
        self.assertEqual(self.eval(V("Array Slice", items, number(1), number(5))), (1.0, 2.0))
        self.assertEqual(self.eval(V("Append To Array", items, arr(4, 5))), (3.0, 1.0, 2.0, 4.0, 5.0))
        self.assertEqual(self.eval(V("Remove From Array", items, arr(1, 3))), (2.0,))
        self.assertEqual(self.eval(V("Index Of Array Value", items, number(2))), 2.0)
        self.assertEqual(self.eval(V("Index Of Array Value", items, number(7))), -1.0)
        self.assertTrue(self.eval(V("Array Contains", items, number(1))))

    def test_element_by_element_values(self):
        items = arr(3, 1, 2)
        element, index = V("Current Array Element"), V("Current Array Index")
        self.assertEqual(
            self.eval(V("Filtered Array", items, V("Compare", element, ">", number(1)))), (3.0, 2.0)
        )
        self.assertEqual(self.eval(V("Sorted Array", items, element)), (1.0, 2.0, 3.0))
        self.assertEqual(self.eval(V("Mapped Array", items, V("Add", element, index))), (3.0, 2.0, 4.0))
        self.assertTrue(self.eval(V("Is True For All", items, V("Compare", element, ">", number(0)))))
        self.assertFalse(self.eval(V("Is True For Any", items, V("Compare", element, ">", number(3)))))
        nested = V(
            "Mapped Array",
            arr(1, 2),
            V("Count Of", V("Filtered Array", arr(1, 2, 3), V("Compare", element, ">", number(1)))),
        )
        self.assertEqual(self.eval(nested), (2.0, 2.0))
        self.assertEqual(self.eval(element), None)

    def test_randomized_array_keeps_every_element(self):
        self.assertEqual(sorted(self.eval(V("Randomized Array", arr(1, 2, 3, 4)))), [1.0, 2.0, 3.0, 4.0])


class TextTests(unittest.TestCase):
    def setUp(self):
        self.eval = Evaluator()

    def test_custom_string_formats_its_values(self):
        value = text("{0} / {1} / {2}", number(2.5), vec(1, 0, 0), V("Hero", "Ana"))
        self.assertEqual(self.eval(value), "2.5 / (1.00, 0.00, 0.00) / Ana")
        self.assertEqual(self.eval(text("{0}{0}", number(3))), "33")
        self.assertEqual(self.eval(text("{1}", number(3))), "null")

    def test_string_functions(self):
        word = text("Workshop")
        self.assertTrue(self.eval(V("String Contains", word, text("shop"))))
        self.assertEqual(self.eval(V("String Length", word)), 8.0)
        self.assertEqual(self.eval(V("String Slice", word, number(4), number(10))), "shop")
        self.assertEqual(self.eval(V("Char In String", word, number(0))), "W")
        self.assertEqual(self.eval(V("Index Of String Char", word, text("k"))), 3.0)
        self.assertEqual(self.eval(V("String Split", text("a,b"), text(","))), ("a", "b"))
        self.assertEqual(self.eval(V("String Replace", word, text("Work"), text("Pit"))), "Pitshop")


class PlayerValueTests(unittest.TestCase):
    def setUp(self):
        self.world = SimpleWorld()
        add = self.world.add_player
        self.one = add(0x80000101, team="Team 1", slot=0, hero="Tracer", position=Vec3(0.0, 0.0, 0.0))
        self.two = add(
            0x80000102, team="Team 1", slot=1, hero="Ana", position=Vec3(5.0, 0.0, 0.0), alive=False
        )
        self.three = add(
            0x80000201,
            team="Team 2",
            slot=0,
            hero="Ana",
            position=Vec3(0.0, 0.0, 3.0),
            facing=Vec3(1.0, 0.0, 0.0),
        )
        self.eval = Evaluator(self.world, player=self.three)

    def test_team_and_life_filters(self):
        self.assertEqual(self.eval(V("All Players", team("All Teams"))), (self.one, self.two, self.three))
        self.assertEqual(self.eval(V("All Living Players", team("Team 1"))), (self.one,))
        self.assertEqual(self.eval(V("All Dead Players", team("All Teams"))), (self.two,))
        self.assertEqual(self.eval(V("Number Of Players", team("Team 2"))), 1.0)
        self.assertEqual(self.eval(V("Opposite Team Of", team("Team 1"))), TEAM_2)
        self.assertEqual(self.eval(V("Team Of", V("Event Player"))), TEAM_2)
        self.assertEqual(self.eval(V("Opposite Team Of", team("All Teams"))), ALL_TEAMS)

    def test_heroes_and_slots(self):
        self.assertEqual(
            self.eval(V("Players On Hero", V("Hero", "Ana"), team("All Teams"))), (self.two, self.three)
        )
        self.assertEqual(self.eval(V("Number Of Heroes", V("Hero", "Ana"), team("Team 1"))), 1.0)
        self.assertEqual(self.eval(V("Players In Slot", number(0), team("Team 2"))), self.three)
        self.assertEqual(
            self.eval(V("Players In Slot", number(0), team("All Teams"))), (self.one, self.three)
        )
        self.assertEqual(self.eval(V("Hero Of", V("Event Player"))), Hero("Ana"))
        self.assertEqual(len(self.eval(V("All Heroes"))), 32)
        self.assertEqual(
            len(self.eval(V("All Tank Heroes")))
            + len(self.eval(V("All Damage Heroes")))
            + len(self.eval(V("All Support Heroes"))),
            32,
        )

    def test_distances_and_view(self):
        origin = vec(0, 0, 0)
        self.assertEqual(self.eval(V("Closest Player To", origin, team("All Teams"))), self.one)
        self.assertEqual(self.eval(V("Farthest Player From", origin, team("All Teams"))), self.three)
        self.assertEqual(
            self.eval(V("Players Within Radius", origin, number(4), team("All Teams"), "Off")),
            (self.one, self.three),
        )
        self.assertEqual(self.eval(V("Distance Between", V("Event Player"), origin)), 3.0)
        self.assertEqual(self.eval(V("Add", V("Event Player"), V("Up"))), Vec3(0.0, 1.0, 3.0))
        self.assertAlmostEqual(self.eval(V("Horizontal Facing Angle Of", V("Event Player"))), 90.0)
        self.assertTrue(self.eval(V("Is In View Angle", V("Event Player"), vec(9, 1.6, 3), number(10))))
        self.assertFalse(self.eval(V("Is In View Angle", V("Event Player"), origin, number(90))))

    def test_world_and_local_vectors_turn_with_the_facing(self):
        local = self.eval(V("Local Vector Of", vec(1, 0, 3), V("Event Player"), "Rotation"))
        self.assertAlmostEqual(local.z, 1.0)
        back = self.eval(V("World Vector Of", vec(0, 0, 1), V("Event Player"), "Rotation And Translation"))
        self.assertAlmostEqual(back.x, 1.0)
        self.assertAlmostEqual(back.z, 3.0)

    def test_world_questions_by_name(self):
        self.assertEqual(self.eval(V("Health", V("Event Player"))), 200.0)
        self.assertTrue(self.eval(V("Is Alive", V("Event Player"))))
        self.assertTrue(self.eval(V("Is Dead", V("First Of", V("All Dead Players", team("All Teams"))))))
        self.assertFalse(self.eval(V("Is Alive", V("Null"))))
        self.assertEqual(self.eval(V("Team Score", team("Team 1"))), 0.0)
        self.assertIsInstance(Team("Team 1"), Team)


class CoverageTests(unittest.TestCase):
    def test_engine_computes_most_values_itself(self):
        self.assertGreaterEqual(len(values.implemented()), 159)

    def test_workshop_settings_use_the_lobby_value_or_the_default(self):
        world = SimpleWorld()
        engine = Engine(Script(settings=((("Game", "Rounds"), 7), (("Game", "Hero"), "Ana"))), world)
        ctx = values.Context(engine, Execution(Rule("probe"), Event("Ongoing - Global")))
        rounds = V("Workshop Setting Integer", text("Game"), text("Rounds"), number(3), number(0), number(5))
        self.assertEqual(ctx.eval(rounds), 5.0)  # the lobby's 7, limited to the setting's maximum
        missing = V("Workshop Setting Real", text("Game"), text("Speed"), number(1.5), number(0), number(9))
        self.assertEqual(ctx.eval(missing), 1.5)
        self.assertEqual(
            ctx.eval(V("Workshop Setting Hero", text("Game"), text("Hero"), V("Hero", "Mercy"))), Hero("Ana")
        )
        self.assertFalse(ctx.eval(V("Workshop Setting Toggle", text("Game"), text("On"), V("False"))))
        self.assertEqual(ctx.eval(V("Server Load")), 0.0)


if __name__ == "__main__":
    unittest.main()
