"""The Workshop rule engine: triggering, flow control, waits, variables, subroutines and chases."""

import unittest

from ow174.game.script.expr import Vec3
from ow174.workshop.engine import (
    TICK_MS,
    Action,
    Blocks,
    Condition,
    Engine,
    Rule,
    Script,
    Unsupported,
    Value,
    WorkshopError,
    default_variable_name,
    number,
    variable_index,
)
from ow174.workshop.values import Hero, team, text
from ow174.workshop.world import SimpleWorld


def G(name):
    return Value("Global Variable", (name,))


def P(player, name):
    return Value("Player Variable", (player, name))


def cmp(left, op, right):
    return Value("Compare", (left, op, right))


def set_g(name, value):
    return Action("Set Global Variable", (name, value))


def add_g(name, value):
    return Action("Modify Global Variable", (name, "Add", value))


def wait(seconds=0.016, behavior="Ignore Condition"):
    return Action("Wait", (number(seconds), behavior))


EVENT_PLAYER = Value("Event Player")


def world_with_players():
    world = SimpleWorld()
    world.add_player(0x80000101, team="Team 1", slot=0, hero="Tracer", name="One")
    world.add_player(0x80000102, team="Team 1", slot=1, hero="Ana", name="Two")
    world.add_player(0x80000201, team="Team 2", slot=0, hero="Doomfist", name="Three")
    return world


def run(rules, frames=1, world=None, **script):
    engine = Engine(Script(rules=tuple(rules), **script), world or SimpleWorld())
    engine.run(frames)
    return engine


class VariableNameTests(unittest.TestCase):
    def test_default_names_cover_the_128_variables(self):
        self.assertEqual(
            [default_variable_name(index) for index in (0, 25, 26, 51, 52, 127)],
            ["A", "Z", "AA", "AZ", "BA", "DX"],
        )
        self.assertEqual(variable_index("DX"), 127)
        self.assertEqual(variable_index("Score", ("A", "Score")), 1)
        for bad in (128, -1, "DY", True, 1.5):
            with self.assertRaises(WorkshopError):
                variable_index(bad)


class BlockTests(unittest.TestCase):
    def test_unmatched_blocks_are_rejected(self):
        for actions in (
            (Action("If", (Value("True"),)),),
            (Action("End"),),
            (Action("Else"),),
            (Action("Break"),),
            (
                Action("If", (Value("True"),)),
                Action("Else"),
                Action("Else If", (Value("True"),)),
                Action("End"),
            ),
        ):
            with self.assertRaises(WorkshopError):
                Blocks(actions)

    def test_disabled_actions_do_not_count_as_block_markers(self):
        blocks = Blocks((Action("If", (Value("True"),)), Action("End", disabled=True), Action("End")))
        self.assertEqual(blocks.opener, {2: 0})


class FlowTests(unittest.TestCase):
    def branch(self, first, second):
        engine = run(
            [
                Rule(
                    "r",
                    actions=(
                        Action("If", (first,)),
                        set_g("A", number(1)),
                        Action("Else If", (second,)),
                        set_g("A", number(2)),
                        Action("Else"),
                        set_g("A", number(3)),
                        Action("End"),
                        add_g("B", number(1)),
                    ),
                )
            ]
        )
        return engine.globals[0], engine.globals[1]

    def test_if_else_if_else_takes_one_branch_then_continues_after_end(self):
        self.assertEqual(self.branch(Value("True"), Value("True")), (1.0, 1.0))
        self.assertEqual(self.branch(Value("False"), Value("True")), (2.0, 1.0))
        self.assertEqual(self.branch(Value("False"), Value("False")), (3.0, 1.0))

    def test_while_with_break_and_continue(self):
        engine = run(
            [
                Rule(
                    "r",
                    actions=(
                        Action("While", (Value("True"),)),
                        add_g("A", number(1)),
                        Action("If", (cmp(G("A"), "==", number(2)),)),
                        Action("Continue"),
                        Action("End"),
                        Action("If", (cmp(G("A"), ">=", number(5)),)),
                        Action("Break"),
                        Action("End"),
                        add_g("B", number(1)),
                        Action("End"),
                    ),
                )
            ]
        )
        self.assertEqual(engine.globals[0], 5.0)
        self.assertEqual(engine.globals[1], 3.0)  # not on 2 (continue) and not on 5 (break)

    def test_for_counts_up_and_down_and_skips_an_empty_range(self):
        def total(start, stop, step):
            engine = run(
                [
                    Rule(
                        "r",
                        actions=(
                            Action("For Global Variable", ("I", number(start), number(stop), number(step))),
                            Action("Modify Global Variable", ("L", "Append To Array", G("I"))),
                            Action("End"),
                        ),
                    )
                ]
            )
            return engine.globals[engine.global_index("L")]

        self.assertEqual(total(0, 3, 1), (0, 0.0, 1.0, 2.0))
        self.assertEqual(total(3, 0, -1), (0, 3.0, 2.0, 1.0))
        self.assertEqual(total(0, 0, 1), 0)
        self.assertEqual(total(0, 5, 0), 0)

    def test_for_player_variable_loops_on_the_player(self):
        world = world_with_players()
        engine = run(
            [
                Rule(
                    "r",
                    event="Ongoing - Each Player",
                    player="Slot 1",
                    actions=(
                        Action("For Player Variable", (EVENT_PLAYER, "I", number(0), number(4), number(2))),
                        add_g("A", number(1)),
                        Action("End"),
                    ),
                )
            ],
            world=world,
        )
        self.assertEqual(engine.globals[0], 2.0)
        self.assertEqual(engine.player_vars[0x80000102][engine.player_index("I")], 4.0)

    def test_skip_and_skip_if(self):
        engine = run(
            [
                Rule(
                    "r",
                    actions=(
                        Action("Skip", (number(1),)),
                        set_g("A", number(1)),
                        Action("Skip If", (Value("False"), number(1))),
                        set_g("B", number(1)),
                        Action("Skip If", (Value("True"), number(1))),
                        set_g("C", number(1)),
                    ),
                )
            ]
        )
        self.assertEqual(engine.globals[:3], [0, 1.0, 0])

    def test_abort_ends_the_rule_and_abort_if_follows_its_value(self):
        engine = run(
            [
                Rule(
                    "r",
                    actions=(
                        Action("Abort If", (Value("False"),)),
                        set_g("A", number(1)),
                        Action("Abort If", (Value("True"),)),
                        set_g("B", number(1)),
                    ),
                )
            ]
        )
        self.assertEqual(engine.globals[:2], [1.0, 0])

    def test_abort_inside_a_called_subroutine_ends_the_caller_too(self):
        engine = run(
            [
                Rule("main", actions=(Action("Call Subroutine", ("Sub",)), set_g("A", number(1)))),
                Rule(
                    "sub",
                    event="Subroutine",
                    subroutine="Sub",
                    actions=(set_g("B", number(1)), Action("Abort")),
                ),
            ]
        )
        self.assertEqual(engine.globals[:2], [0, 1.0])

    def test_loop_restarts_the_action_list_after_a_wait(self):
        engine = run([Rule("r", actions=(add_g("A", number(1)), wait(), Action("Loop")))], frames=4)
        self.assertEqual(engine.globals[0], 4.0)

    def test_loop_without_a_wait_is_an_infinite_loop(self):
        with self.assertRaises(WorkshopError) as raised:
            run([Rule("spin", actions=(add_g("A", number(1)), Action("Loop")))])
        self.assertIn("without waiting", str(raised.exception))


class WaitTests(unittest.TestCase):
    def test_wait_holds_the_rule_until_its_time(self):
        engine = Engine(Script(rules=(Rule("r", actions=(wait(0.1), set_g("A", number(1)))),)), SimpleWorld())
        frames = 0
        while engine.globals[0] == 0:
            engine.tick()
            frames += 1
        self.assertEqual(frames, 8)  # resumes in the first frame at or after 100 ms (frame 7 = 112 ms)
        self.assertEqual(TICK_MS, 16)

    def test_shortest_wait_is_one_frame(self):
        engine = run([Rule("r", actions=(wait(0), set_g("A", number(1))))])
        self.assertEqual(engine.globals[0], 0)
        engine.tick()
        self.assertEqual(engine.globals[0], 1.0)

    def test_abort_when_false_ends_the_rule_when_its_conditions_fail(self):
        rule = Rule(
            "r",
            conditions=(Condition(G("Go"), "==", Value("True")),),
            actions=(wait(1, "Abort When False"), set_g("A", number(1))),
        )
        engine = Engine(Script(rules=(rule,), global_names=("Go",)), SimpleWorld())
        engine.globals[0] = True
        engine.tick()
        engine.globals[0] = False
        engine.run(100)
        self.assertEqual(engine.globals[1], 0)

    def test_restart_when_true_starts_over_when_the_conditions_return(self):
        rule = Rule(
            "r",
            conditions=(Condition(G("Go"), "==", Value("True")),),
            actions=(add_g("Runs", number(1)), wait(1, "Restart When True")),
        )
        engine = Engine(Script(rules=(rule,), global_names=("Go", "Runs")), SimpleWorld())
        engine.globals[0] = True
        engine.tick()
        engine.globals[0] = False
        engine.tick()
        engine.globals[0] = True
        engine.tick()
        self.assertEqual(engine.globals[1], 2.0)

    def test_wait_until_ends_early_when_its_condition_holds(self):
        rule = Rule(
            "r",
            actions=(Action("Wait Until", (cmp(G("B"), "==", number(1)), number(99))), set_g("A", number(1))),
        )
        engine = run([rule], frames=3)
        self.assertEqual(engine.globals[0], 0)
        engine.globals[1] = 1.0
        engine.tick()
        self.assertEqual(engine.globals[0], 1.0)


class TriggerTests(unittest.TestCase):
    def test_ongoing_rule_runs_again_only_after_its_conditions_were_false(self):
        rule = Rule(
            "r", conditions=(Condition(G("Go"), "==", Value("True")),), actions=(add_g("Runs", number(1)),)
        )
        engine = Engine(Script(rules=(rule,), global_names=("Go", "Runs")), SimpleWorld())
        engine.run(3)
        self.assertEqual(engine.globals[1], 0)
        engine.globals[0] = True
        engine.run(3)
        self.assertEqual(engine.globals[1], 1.0)
        engine.globals[0] = False
        engine.tick()
        engine.globals[0] = True
        engine.run(3)
        self.assertEqual(engine.globals[1], 2.0)

    def test_each_player_rules_filter_by_team_slot_and_hero(self):
        def players(**filters):
            engine = run(
                [
                    Rule(
                        "r",
                        event="Ongoing - Each Player",
                        actions=(
                            Action(
                                "Modify Global Variable",
                                ("A", "Append To Array", Value("Slot Of", (EVENT_PLAYER,))),
                            ),
                        ),
                        **filters,
                    )
                ],
                world=world_with_players(),
            )
            return engine.globals[0]

        self.assertEqual(players(), (0, 0.0, 1.0, 0.0))
        self.assertEqual(players(team="Team 2"), (0, 0.0))
        self.assertEqual(players(player="Slot 1"), (0, 1.0))
        self.assertEqual(players(player="Doomfist"), (0, 0.0))

    def test_player_events_run_with_their_event_values(self):
        world = world_with_players()
        rule = Rule(
            "r",
            event="Player Took Damage",
            actions=(
                set_g("A", Value("Event Damage")),
                set_g("B", Value("Attacker")),
                set_g("C", EVENT_PLAYER),
            ),
        )
        engine = Engine(Script(rules=(rule,)), world)
        victim, attacker = world.players()[0], world.players()[2]
        engine.fire("Player Took Damage", victim, Attacker=attacker, **{"Event Damage": 30.0})
        engine.tick()
        self.assertEqual(engine.globals[:3], [30.0, attacker, victim])
        with self.assertRaises(WorkshopError):
            engine.fire("Ongoing - Global", victim)

    def test_a_player_who_leaves_stops_their_rules(self):
        world = world_with_players()
        rule = Rule(
            "r", event="Ongoing - Each Player", player="Slot 1", actions=(wait(1), set_g("A", number(1)))
        )
        engine = run([rule], world=world)
        world.remove_player(world.players()[1])
        engine.run(100)
        self.assertEqual(engine.globals[0], 0)

    def test_disabled_rules_conditions_and_actions_are_skipped(self):
        engine = run(
            [
                Rule("off", disabled=True, actions=(set_g("A", number(1)),)),
                Rule(
                    "on",
                    conditions=(Condition(Value("False"), "==", Value("True"), disabled=True),),
                    actions=(
                        Action("Set Global Variable", ("B", number(1)), disabled=True),
                        set_g("C", number(1)),
                    ),
                ),
            ]
        )
        self.assertEqual(engine.globals[:3], [0, 0, 1.0])

    def test_rules_run_in_script_order_within_a_frame(self):
        engine = run(
            [
                Rule("first", actions=(set_g("A", number(1)),)),
                Rule(
                    "second",
                    conditions=(Condition(G("A"), "==", number(1)),),
                    actions=(set_g("B", number(1)),),
                ),
            ]
        )
        self.assertEqual(engine.globals[1], 1.0)


class SubroutineTests(unittest.TestCase):
    def test_call_subroutine_runs_it_in_place_with_the_callers_event_player(self):
        world = world_with_players()
        engine = run(
            [
                Rule(
                    "main",
                    event="Ongoing - Each Player",
                    player="Slot 1",
                    actions=(Action("Call Subroutine", ("Sub",)), add_g("B", number(1))),
                ),
                Rule("sub", event="Subroutine", subroutine="Sub", actions=(set_g("A", EVENT_PLAYER),)),
            ],
            world=world,
        )
        self.assertEqual(engine.globals[:2], [world.players()[1], 1.0])

    def test_start_rule_restarts_or_leaves_a_running_subroutine(self):
        def runs(behavior):
            engine = run(
                [
                    Rule(
                        "main",
                        actions=(
                            Action("Start Rule", ("Sub", behavior)),
                            wait(),
                            Action("Start Rule", ("Sub", behavior)),
                        ),
                    ),
                    Rule(
                        "sub", event="Subroutine", subroutine="Sub", actions=(add_g("A", number(1)), wait(5))
                    ),
                ],
                frames=3,
            )
            return engine.globals[0]

        self.assertEqual(runs("Restart Rule"), 2.0)
        self.assertEqual(runs("Do Nothing"), 1.0)

    def test_unknown_subroutine_is_an_error(self):
        with self.assertRaises(WorkshopError):
            run([Rule("main", actions=(Action("Call Subroutine", ("Nope",)),))])


class VariableActionTests(unittest.TestCase):
    def test_modify_operations(self):
        def result(start, operation, operand):
            engine = run(
                [
                    Rule(
                        "r",
                        actions=(
                            set_g("A", start),
                            Action("Modify Global Variable", ("A", operation, operand)),
                        ),
                    )
                ]
            )
            return engine.globals[0]

        array = Value("Array", (number(1), number(2), number(1)))
        self.assertEqual(result(number(7), "Subtract", number(2)), 5.0)
        self.assertEqual(result(number(7), "Divide", number(0)), 0.0)
        self.assertEqual(result(number(7), "Modulo", number(4)), 3.0)
        self.assertEqual(result(number(2), "Raise To Power", number(10)), 1024.0)
        self.assertEqual(result(number(2), "Max", number(9)), 9.0)
        self.assertEqual(result(array, "Remove From Array By Value", number(1)), (2.0,))
        self.assertEqual(result(array, "Remove From Array By Index", number(1)), (1.0, 1.0))
        self.assertEqual(result(Value("Empty Array"), "Append To Array", array), (1.0, 2.0, 1.0))

    def test_at_index_grows_the_array_with_zeros(self):
        engine = run(
            [
                Rule(
                    "r",
                    actions=(
                        Action("Set Global Variable At Index", ("A", number(2), number(5))),
                        Action("Modify Global Variable At Index", ("A", number(2), "Multiply", number(3))),
                    ),
                )
            ]
        )
        self.assertEqual(engine.globals[0], (0, 0, 15.0))

    def test_player_variables_apply_to_each_player_of_an_array(self):
        world = world_with_players()
        engine = run(
            [
                Rule(
                    "r",
                    actions=(
                        Action(
                            "Set Player Variable", (Value("All Players", (team("Team 1"),)), "X", number(4))
                        ),
                        set_g("A", P(Value("First Of", (Value("All Players", (team("Team 1"),)),)), "X")),
                    ),
                )
            ],
            world=world,
        )
        x = engine.player_index("X")
        self.assertEqual([engine.player_vars.get(p.id, [0] * 128)[x] for p in world.players()], [4.0, 4.0, 0])
        self.assertEqual(engine.globals[0], 4.0)

    def test_chase_over_time_and_at_rate(self):
        engine = run(
            [
                Rule(
                    "r",
                    actions=(
                        Action("Chase Global Variable Over Time", ("A", number(10), number(0.16), "None")),
                        Action("Chase Global Variable At Rate", ("B", number(-1), number(6.25), "None")),
                    ),
                )
            ],
            frames=11,
        )
        self.assertEqual(engine.globals[0], 10.0)
        self.assertAlmostEqual(engine.globals[1], -0.9999999999, places=6)
        self.assertEqual(engine.chases, {})

    def test_stop_chasing_keeps_the_value_reached(self):
        engine = run(
            [
                Rule(
                    "r",
                    actions=(
                        Action("Chase Global Variable At Rate", ("A", number(100), number(62.5), "None")),
                        wait(),
                        Action("Stop Chasing Global Variable", ("A",)),
                    ),
                )
            ],
            frames=5,
        )
        self.assertEqual(engine.globals[0], 1.0)  # chases move at the start of a frame: one step

    def test_log_to_inspector(self):
        world = SimpleWorld()
        engine = run(
            [Rule("r", actions=(Action("Log To Inspector", (text("x={0}", number(2.5)),)),))], world=world
        )
        self.assertEqual(engine.log, ["x=2.5"])
        self.assertEqual(world.logged, ["x=2.5"])


class WorldActionTests(unittest.TestCase):
    def test_world_actions_get_their_evaluated_parameters(self):
        world = world_with_players()
        run(
            [
                Rule(
                    "r",
                    actions=(
                        Action(
                            "Teleport",
                            (
                                Value("Players On Hero", (Value("Hero", ("Doomfist",)), team("All Teams"))),
                                Value("Vector", (number(1), number(2), number(3))),
                            ),
                        ),
                        Action(
                            "Big Message",
                            (Value("All Players", (team("Team 1"),)), text("Hi {0}", number(2))),
                        ),
                    ),
                )
            ],
            world=world,
        )
        self.assertEqual(world.state(world.players()[2]).position, Vec3(1.0, 2.0, 3.0))
        self.assertEqual(world.messages, [("big", tuple(world.players()[:2]), "Hi 2")])

    def test_kill_reports_died_and_elimination_events(self):
        world = world_with_players()
        one, _, three = world.players()
        engine = run(
            [
                Rule(
                    "kill",
                    actions=(
                        Action(
                            "Kill",
                            (
                                Value("Players On Hero", (Value("Hero", ("Doomfist",)),)),
                                Value("First Of", (Value("All Players", (team("Team 1"),)),)),
                            ),
                        ),
                    ),
                ),
                Rule(
                    "died",
                    event="Player Died",
                    actions=(set_g("A", EVENT_PLAYER), set_g("B", Value("Attacker"))),
                ),
                Rule("elim", event="Player Earned Elimination", actions=(set_g("C", Value("Victim")),)),
            ],
            frames=2,
            world=world,
        )
        self.assertEqual(engine.globals[:3], [three, one, three])

    def test_unknown_world_action_and_value_stop_the_script(self):
        with self.assertRaises(Unsupported) as raised:
            run([Rule("r", actions=(Action("Create Effect", ()),))])
        self.assertEqual((raised.exception.kind, raised.exception.name), ("action", "Create Effect"))
        with self.assertRaises(Unsupported) as raised:
            run([Rule("r", actions=(set_g("A", Value("Match Time")),))])
        self.assertEqual((raised.exception.kind, raised.exception.name), ("value", "Match Time"))

    def test_heroes_compare_by_name(self):
        world = world_with_players()
        engine = run(
            [
                Rule(
                    "r",
                    event="Ongoing - Each Player",
                    conditions=(Condition(Value("Hero Of", (EVENT_PLAYER,)), "==", Value("Hero", ("Ana",))),),
                    actions=(set_g("A", EVENT_PLAYER),),
                )
            ],
            world=world,
        )
        self.assertEqual(engine.globals[0], world.players()[1])
        self.assertEqual(Hero("Ana"), Value("Hero", ("Ana",)).args and Hero("Ana"))


if __name__ == "__main__":
    unittest.main()
