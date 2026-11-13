"""The Workshop rule engine: rules, conditions, actions and flow control of build 104319 scripts.

A script is a list of rules. A rule has an event, an optional player filter, conditions and actions. This
module runs scripts written in the catalog's own names (the names DataTool's `list-workshop` gives), for
example::

    Rule("Hello", conditions=(Condition(Value("Global Variable", (0,)), "==", number(1)),),
         actions=(Action("Big Message", (Value("All Players", (team("All Teams"),)), text("Hello"))),))

The engine owns time, rule triggering, the action pointer of every running rule, waits, flow control,
subroutines and the 128 global and 128 per-player variables. Values are computed by ow174.workshop.values.
Everything that touches the game itself (players, positions, messages, effects, damage) goes through a
World: the engine never assumes a game server. world.SimpleWorld is an in-memory world for tests; a world
that runs the client's own action graphs is in ow174.workshop.graph_world.

Behaviour that comes from the Workshop's public documentation and in-game descriptions, not from client
code: when an ongoing rule fires again, what Abort does inside a subroutine, how a second event for a
player whose rule is still running is treated, and when a For loop evaluates its range. Each choice is
named where it is made, and docs/WORKSHOP_ENGINE.txt lists them. Nothing here has been compared with a
retail server, which no longer exists.
"""

import math
from dataclasses import dataclass, field

from ow174.game.script.expr import Entity

TICK_MS = 16  # one server frame at 62.5 Hz
MIN_WAIT_MS = 16  # the action graphs limit Wait to 0.016 s
MAX_STEPS = 10_000  # actions one rule may run in one frame before the engine calls it an infinite loop
VARIABLES = 128

EVENTS = (
    "Ongoing - Global",
    "Ongoing - Each Player",
    "Player Earned Elimination",
    "Player Dealt Final Blow",
    "Player Dealt Damage",
    "Player Took Damage",
    "Player Died",
    "Player Dealt Healing",
    "Player Received Healing",
    "Player Joined Match",
    "Player Left Match",
    "Subroutine",
    "Player Dealt Knockback",
    "Player Received Knockback",
)
ONGOING_GLOBAL, ONGOING_EACH_PLAYER, SUBROUTINE = EVENTS[0], EVENTS[1], EVENTS[11]
PLAYER_EVENTS = frozenset(EVENTS) - {ONGOING_GLOBAL, ONGOING_EACH_PLAYER, SUBROUTINE}
WAIT_BEHAVIORS = ("Ignore Condition", "Abort When False", "Restart When True")
OPERATORS = ("==", "!=", "<", "<=", ">", ">=")
MODIFY_OPERATIONS = (
    "Add",
    "Subtract",
    "Multiply",
    "Divide",
    "Modulo",
    "Raise To Power",
    "Min",
    "Max",
    "Append To Array",
    "Remove From Array By Value",
    "Remove From Array By Index",
)
BLOCK_OPENERS = frozenset(("If", "While", "For Global Variable", "For Player Variable"))
LOOPS = frozenset(("While", "For Global Variable", "For Player Variable"))


class WorkshopError(RuntimeError):
    """A script the engine cannot run: unmatched blocks, an infinite loop, a bad variable."""


class Unsupported(WorkshopError):
    """A value or action that neither the engine nor the world implements."""

    def __init__(self, kind: str, name: str) -> None:
        self.kind, self.name = kind, name
        super().__init__(f"unsupported {kind}: {name}")


# --- the script --------------------------------------------------------------------------------


@dataclass(frozen=True)
class Value:
    """A value of the catalog by name, with its parameters: Values or constants (numbers, dropdown option
    names, variable indexes or names, hero, team, button and map names, text)."""

    name: str
    args: tuple = ()


@dataclass(frozen=True)
class Condition:
    left: object
    op: str
    right: object
    disabled: bool = False


@dataclass(frozen=True)
class Action:
    name: str
    args: tuple = ()
    disabled: bool = False
    comment: str = ""


@dataclass(frozen=True)
class Rule:
    name: str
    event: str = ONGOING_GLOBAL
    team: str = "All"  # player events: "All", "Team 1" or "Team 2"
    player: str = "All"  # player events: "All", "Slot 0".."Slot 11" or a hero name
    subroutine: str | None = None  # the Subroutine event's subroutine name
    conditions: tuple = ()
    actions: tuple = ()
    disabled: bool = False


@dataclass(frozen=True)
class Script:
    rules: tuple = ()
    global_names: tuple = ()  # variable names by index; unnamed slots use the default names A..DX
    player_names: tuple = ()
    subroutines: tuple = ()  # subroutine names by index
    settings: tuple = ()  # Workshop Settings the lobby set: ((category, name), value) pairs


def number(value: float) -> Value:
    return Value("Number", (float(value),))


def default_variable_name(index: int) -> str:
    """A..Z, then AA..DX: the Workshop's 128 default variable names."""
    if index < 26:
        return chr(65 + index)
    index -= 26
    return chr(65 + index // 26) + chr(65 + index % 26)


DEFAULT_NAMES = {default_variable_name(index): index for index in range(VARIABLES)}


def variable_index(reference, names: tuple = ()) -> int:
    """A variable parameter (an index, a script name or a default name) as an index 0..127."""
    if isinstance(reference, bool):
        raise WorkshopError(f"bad variable reference {reference!r}")
    if isinstance(reference, int):
        index = reference
    elif isinstance(reference, str) and reference in names:
        index = names.index(reference)
    elif isinstance(reference, str) and reference in DEFAULT_NAMES:
        index = DEFAULT_NAMES[reference]
    else:
        raise WorkshopError(f"bad variable reference {reference!r}")
    if not 0 <= index < VARIABLES:
        raise WorkshopError(f"variable index {index} out of range")
    return index


# --- running rules -----------------------------------------------------------------------------


@dataclass(frozen=True)
class Event:
    """What started a rule: the event, the event player and the event's values ("Attacker", "Victim",
    "Event Damage", "Event Healing", "Event Was Critical Hit", "Event Direction", "Event Ability",
    "Healer", "Healee", "Event Was Health Pack", "Event Was Environment")."""

    name: str
    player: Entity | None = None
    values: tuple = ()  # (name, value) pairs

    def value(self, name: str, default=None):
        for key, value in self.values:
            if key == name:
                return value
        return default


class Blocks:
    """The block structure of one action list: where each If, Else If, Else, While, For and End jumps."""

    def __init__(self, actions: tuple) -> None:
        self.end: dict[int, int] = {}  # opener, Else If or Else -> its End
        self.next: dict[int, int] = {}  # If or Else If -> the next Else If, Else or End
        self.opener: dict[int, int] = {}  # End -> its opener
        self.loop: dict[int, int] = {}  # Break or Continue -> the innermost enclosing loop opener
        stack: list[list[int]] = []  # [opener, last branch]
        loops: list[int] = []
        for position, action in enumerate(actions):
            if action.disabled:
                continue
            name = action.name
            if name in BLOCK_OPENERS:
                stack.append([position, position])
                if name in LOOPS:
                    loops.append(position)
            elif name in ("Else If", "Else"):
                if not stack or actions[stack[-1][0]].name != "If":
                    raise WorkshopError(f"{name} at action {position} is not inside an If")
                if actions[stack[-1][1]].name == "Else":
                    raise WorkshopError(f"{name} at action {position} follows an Else")
                self.next[stack[-1][1]] = position
                stack[-1][1] = position
            elif name == "End":
                if not stack:
                    raise WorkshopError(f"End at action {position} closes no block")
                opener, last = stack.pop()
                if actions[last].name != "Else":
                    self.next[last] = position
                for branch in self._branches(actions, opener):
                    self.end[branch] = position
                self.opener[position] = opener
                if opener in loops:
                    loops.remove(opener)
            elif name in ("Break", "Continue"):
                if not loops:
                    raise WorkshopError(f"{name} at action {position} is not inside a loop")
                self.loop[position] = loops[-1]
        if stack:
            raise WorkshopError(f"{actions[stack[-1][0]].name} at action {stack[-1][0]} has no End")

    def _branches(self, actions: tuple, opener: int) -> list[int]:
        branches, position = [opener], opener
        while position in self.next and actions[self.next[position]].name in ("Else If", "Else"):
            position = self.next[position]
            branches.append(position)
        return branches


@dataclass
class Frame:
    """One action list being run: a rule's or a called subroutine's."""

    actions: tuple
    blocks: Blocks
    pc: int = 0


@dataclass
class Wait:
    until_ms: int
    behavior: str = "Ignore Condition"
    condition: object = None  # Wait Until: the condition to wait for
    was_true: bool = True  # Restart When True: the rule's conditions at the previous frame


@dataclass
class Execution:
    """One running rule: its event, its frames and what it waits for."""

    rule: Rule
    event: Event
    frames: list = field(default_factory=list)
    wait: Wait | None = None
    pending: object = None  # a world action that has not finished
    finished: bool = False
    current: list = field(default_factory=list)  # Current Array Element / Index, innermost last

    @property
    def player(self) -> Entity | None:
        return self.event.player


@dataclass
class Slot:
    """The trigger state of an ongoing rule for one player (or for the game)."""

    execution: Execution | None = None
    armed: bool = True  # the conditions were false since the rule last started (or it never ran)


@dataclass
class Chase:
    target: tuple  # ("global", index) or ("player", entity id, index)
    destination: object
    amount: object  # a rate per second, or a duration in seconds
    over_time: bool
    reevaluate: bool
    execution: Execution
    start_ms: int = 0
    start_value: object = None
    fixed_destination: object = None
    fixed_amount: float = 0.0


class Engine:
    """Runs one script against one world, one frame at a time."""

    def __init__(self, script: Script, world) -> None:
        from ow174.workshop import values  # the values module imports this one

        self.values = values
        self.script = script
        self.world = world
        self.now = 0  # milliseconds since the script started
        self.frame = 0
        self.globals: list = [0] * VARIABLES
        self.player_vars: dict[int, list] = {}
        self.slots: dict[tuple, Slot] = {}
        self.executions: list[Execution] = []
        self.started: dict[tuple, Execution] = {}  # (rule, player id) -> event or Start Rule execution
        self.chases: dict[tuple, Chase] = {}
        self.events: list[Event] = []
        self.rule_order = {rule: index for index, rule in enumerate(script.rules)}
        self.blocks = {rule: Blocks(rule.actions) for rule in script.rules}
        self.subroutines = {
            rule.subroutine: rule for rule in script.rules if rule.event == SUBROUTINE and not rule.disabled
        }
        self.log: list[str] = []
        self.steps = 0
        self.frame_steps: list[int] = []  # actions run in each of the recent frames (Server Load)
        self.settings = dict(script.settings)
        world.attach(self)

    # --- variables -------------------------------------------------------------------------------

    def global_index(self, reference) -> int:
        return variable_index(reference, self.script.global_names)

    def player_index(self, reference) -> int:
        return variable_index(reference, self.script.player_names)

    def player_variables(self, player) -> list:
        entity = self.values.entity_of(player)
        if entity is None:
            raise WorkshopError("a player variable of no player")
        return self.player_vars.setdefault(entity.id, [0] * VARIABLES)

    def read(self, target: tuple):
        if target[0] == "global":
            return self.globals[target[1]]
        return self.player_vars.get(target[1], [0] * VARIABLES)[target[2]]

    def write(self, target: tuple, value) -> None:
        if target[0] == "global":
            self.globals[target[1]] = value
        else:
            self.player_vars.setdefault(target[1], [0] * VARIABLES)[target[2]] = value

    # --- events and frames ---------------------------------------------------------------------

    def fire(self, name: str, player: Entity, **values) -> None:
        """Report a player event; matching rules start at the next frame."""
        if name not in PLAYER_EVENTS:
            raise WorkshopError(f"{name!r} is not a player event")
        self.events.append(Event(name, player, tuple(values.items())))

    def run(self, frames: int) -> None:
        for _ in range(frames):
            self.tick()

    def tick(self) -> None:
        """One frame. Chases move first; then, rule by rule in script order, the rule may start and its
        running instances continue until they wait or end, so a later rule sees what an earlier one did
        in the same frame."""
        self.world.begin_frame(self)
        steps_before = self.steps
        self._update_chases()
        events, self.events = self.events, []
        players = list(self.world.players())
        present = {player.id for player in players}
        for execution in self.executions:
            player = execution.player
            if (
                player is not None
                and player.id not in present
                and execution.event.name != "Player Left Match"
            ):
                execution.finished = True  # the player left: their rules stop
        for rule in self.script.rules:
            if not rule.disabled:
                self._trigger(rule, players, events)
            for execution in [item for item in self.executions if item.rule is rule]:
                if not execution.finished:
                    self._continue(execution)
            self.executions = [execution for execution in self.executions if not execution.finished]
        self.frame_steps = [*self.frame_steps[-59:], self.steps - steps_before]
        self.world.end_frame(self)
        self.frame += 1
        self.now += TICK_MS

    def _trigger(self, rule: Rule, players: list, events: list) -> None:
        if rule.event == ONGOING_GLOBAL:
            self._ongoing(rule, None)
        elif rule.event == ONGOING_EACH_PLAYER:
            for player in players:
                if self._matches(rule, player):
                    self._ongoing(rule, player)
        elif rule.event != SUBROUTINE:
            for event in events:
                if (
                    event.name == rule.event
                    and event.player is not None
                    and self._matches(rule, event.player)
                ):
                    self._event(rule, event)

    def _matches(self, rule: Rule, player: Entity) -> bool:
        if rule.team != "All" and self.world.team_of(player) != rule.team:
            return False
        if rule.player == "All":
            return True
        if rule.player.startswith("Slot "):
            return self.world.slot_of(player) == int(rule.player[5:])
        hero = self.world.hero_of(player)
        return hero is not None and getattr(hero, "name", hero) == rule.player

    def conditions(self, execution: Execution) -> bool:
        """Whether every enabled condition of the execution's rule holds now."""
        ctx = self.values.Context(self, execution)
        for condition in execution.rule.conditions:
            if not condition.disabled and not self.values.compare(
                ctx, ctx.eval(condition.left), condition.op, ctx.eval(condition.right)
            ):
                return False
        return True

    def _ongoing(self, rule: Rule, player: Entity | None) -> None:
        """An ongoing rule starts when its conditions hold and have not held since it last started.
        (Assumption: conditions seen false while the rule runs re-arm it for when it ends.)"""
        key = (rule, player.id if player is not None else None)
        slot = self.slots.setdefault(key, Slot())
        if slot.execution is not None and slot.execution.finished:
            slot.execution = None
        probe = Execution(rule, Event(rule.event, player))
        holds = self.conditions(probe)
        if not holds:
            slot.armed = True
        elif slot.execution is None and slot.armed:
            slot.armed = False
            slot.execution = self._start(rule, probe.event)

    def _event(self, rule: Rule, event: Event) -> None:
        """A player event starts the rule for its player when the conditions hold. (Assumption: while the
        rule still runs for that player, the event is ignored.)"""
        key = (rule, event.player.id)
        running = self.started.get(key)
        if running is not None and not running.finished:
            return
        probe = Execution(rule, event)
        if self.conditions(probe):
            self.started[key] = self._start(rule, event)

    def _start(self, rule: Rule, event: Event) -> Execution:
        execution = Execution(rule, event, [Frame(rule.actions, self.blocks[rule])])
        self.executions.append(execution)
        return execution

    def start_rule(self, name: str, caller: Execution, restart: bool) -> None:
        """Start Rule: run a subroutine as its own rule for the caller's event player."""
        rule = self._subroutine(name)
        key = (rule, caller.player.id if caller.player is not None else None)
        running = self.started.get(key)
        if running is not None and not running.finished:
            if not restart:
                return
            running.finished = True
        execution = Execution(rule, caller.event, [Frame(rule.actions, self.blocks[rule])])
        self.started[key] = execution
        self.executions.append(execution)
        # It runs in this frame when its rule comes after the caller's; otherwise in the next one.

    def _subroutine(self, name: str) -> Rule:
        rule = self.subroutines.get(name)
        if rule is None:
            raise WorkshopError(f"no subroutine named {name!r}")
        return rule

    # --- running actions -----------------------------------------------------------------------

    def _continue(self, execution: Execution) -> None:
        if execution.pending is not None:
            if not getattr(execution.pending, "done", True):
                return
            execution.pending = None
        wait = execution.wait
        if wait is not None:
            if wait.behavior == "Abort When False" and not self.conditions(execution):
                execution.finished = True
                return
            if wait.behavior == "Restart When True":
                holds = self.conditions(execution)
                if holds and not wait.was_true:
                    self._restart(execution)
                    return
                wait.was_true = holds
            if wait.condition is not None:
                ctx = self.values.Context(self, execution)
                if self.values.truthy(ctx.eval(wait.condition)):
                    execution.wait = None
            if execution.wait is not None:
                if self.now < wait.until_ms:
                    return
                execution.wait = None
        self._step(execution)

    def _restart(self, execution: Execution) -> None:
        del execution.frames[1:]
        execution.frames[0].pc = 0
        execution.wait = None
        self._step(execution)

    def _step(self, execution: Execution) -> None:
        """Run actions until the rule waits, waits for the world, or ends."""
        steps = 0
        while not execution.finished and execution.wait is None and execution.pending is None:
            frame = execution.frames[-1]
            if frame.pc >= len(frame.actions):
                execution.frames.pop()
                if not execution.frames:
                    execution.finished = True
                    return
                execution.frames[-1].pc += 1
                continue
            steps += 1
            self.steps += 1
            if steps > MAX_STEPS:
                raise WorkshopError(
                    f"rule {execution.rule.name!r} ran {MAX_STEPS} actions in one frame without waiting"
                )
            action = frame.actions[frame.pc]
            if action.disabled:
                frame.pc += 1
                continue
            self._action(execution, frame, action)

    def _action(self, execution: Execution, frame: Frame, action: Action) -> None:
        """Flow control and variables are the engine's; every other action is the world's. A world
        action that has not finished (`done` is false) holds the rule until it has."""
        ctx = self.values.Context(self, execution)
        handler = FLOW.get(action.name)
        if handler is not None:
            handler(self, ctx, execution, frame, action)
            return
        native = NATIVE.get(action.name)
        frame.pc += 1
        if native is not None:
            native(self, ctx, action)
            return
        result = self.world.action(ActionCall(action.name, action.args, ctx))
        if result is not None and not getattr(result, "done", True):
            execution.pending = result

    # --- chases ------------------------------------------------------------------------------------

    def chase(
        self, target: tuple, destination, amount, over_time: bool, reevaluate: bool, execution: Execution
    ) -> None:
        chase = Chase(
            target, destination, amount, over_time, reevaluate, execution, self.now, self.read(target)
        )
        ctx = self.values.Context(self, execution)
        chase.fixed_destination = ctx.eval(destination)
        chase.fixed_amount = self.values.to_number(ctx.eval(amount))
        self.chases[target] = chase

    def stop_chase(self, target: tuple) -> None:
        self.chases.pop(target, None)

    def _update_chases(self) -> None:
        for target, chase in list(self.chases.items()):
            ctx = self.values.Context(self, chase.execution)
            if chase.reevaluate:
                destination = ctx.eval(chase.destination)
                amount = self.values.to_number(ctx.eval(chase.amount))
            else:
                destination, amount = chase.fixed_destination, chase.fixed_amount
            current = self.read(target)
            if chase.over_time:
                elapsed = (self.now - chase.start_ms) / 1000.0 + TICK_MS / 1000.0
                if chase.reevaluate:
                    remaining = amount - (self.now - chase.start_ms) / 1000.0
                    share = 1.0 if remaining <= TICK_MS / 1000.0 else (TICK_MS / 1000.0) / remaining
                    value = self.values.interpolate(ctx, current, destination, share)
                    done = remaining <= TICK_MS / 1000.0
                else:
                    share = 1.0 if amount <= 0 else min(elapsed / amount, 1.0)
                    value = self.values.interpolate(ctx, chase.start_value, destination, share)
                    done = share >= 1.0
            else:
                value = self.values.approach(ctx, current, destination, amount * TICK_MS / 1000.0)
                done = not chase.reevaluate and self.values.compare(ctx, value, "==", destination)
            self.write(target, value)
            if done:
                del self.chases[target]


@dataclass
class ActionCall:
    """An action the world performs: its name, its parameters and the context to evaluate them in.
    `value(i)` evaluates parameter i now, so a world can evaluate a parameter again later."""

    name: str
    args: tuple
    ctx: object

    def value(self, index: int):
        return self.ctx.eval(self.args[index]) if index < len(self.args) else None

    def values(self) -> tuple:
        return tuple(self.value(index) for index in range(len(self.args)))

    @property
    def execution(self) -> Execution:
        return self.ctx.execution


# --- flow control ------------------------------------------------------------------------------


def _truth(ctx, action: Action, index: int = 0) -> bool:
    return ctx.truthy(ctx.eval(action.args[index])) if index < len(action.args) else False


def _if(engine, ctx, execution, frame, action) -> None:
    position = frame.pc
    while True:
        node = frame.actions[position]
        if node.name == "Else":
            frame.pc = position + 1
            return
        if node.name == "End":
            frame.pc = position + 1
            return
        if _truth(ctx, node):
            frame.pc = position + 1
            return
        position = frame.blocks.next[position]


def _branch_end(engine, ctx, execution, frame, action) -> None:
    frame.pc = frame.blocks.end[frame.pc] + 1  # the previous branch ran: leave the If


def _while(engine, ctx, execution, frame, action) -> None:
    frame.pc = frame.pc + 1 if _truth(ctx, action) else frame.blocks.end[frame.pc] + 1


def _for_target(engine, ctx, action: Action) -> tuple:
    if action.name == "For Global Variable":
        return ("global", engine.global_index(action.args[0])), action.args[1:]
    player = ctx.eval(action.args[0])
    entity = engine.values.entity_of(player)
    if entity is None:
        raise WorkshopError("For Player Variable of no player")
    return ("player", entity.id, engine.player_index(action.args[1])), action.args[2:]


def _for_continues(engine, ctx, value, stop, step) -> bool:
    current, stop, step = (engine.values.to_number(item) for item in (value, stop, step))
    return current < stop if step > 0 else current > stop if step < 0 else False


def _for(engine, ctx, execution, frame, action) -> None:
    """For: the variable starts at the range start; the loop runs while it is short of the range stop,
    moving by the step at each End. (Assumption: stop and step are evaluated again at every check.)"""
    target, (start, stop, step) = _for_target(engine, ctx, action)
    value = engine.values.to_number(ctx.eval(start))
    engine.write(target, value)
    if _for_continues(engine, ctx, value, ctx.eval(stop), ctx.eval(step)):
        frame.pc += 1
    else:
        frame.pc = frame.blocks.end[frame.pc] + 1


def _end(engine, ctx, execution, frame, action) -> None:
    opener_position = frame.blocks.opener[frame.pc]
    opener = frame.actions[opener_position]
    if opener.name == "While":
        frame.pc = opener_position
    elif opener.name in ("For Global Variable", "For Player Variable"):
        target, (_, stop, step) = _for_target(engine, ctx, opener)
        step_value = ctx.eval(step)
        value = engine.values.to_number(engine.read(target)) + engine.values.to_number(step_value)
        engine.write(target, value)
        if _for_continues(engine, ctx, value, ctx.eval(stop), step_value):
            frame.pc = opener_position + 1
        else:
            frame.pc += 1
    else:
        frame.pc += 1


def _break(engine, ctx, execution, frame, action) -> None:
    frame.pc = frame.blocks.end[frame.blocks.loop[frame.pc]] + 1


def _continue_loop(engine, ctx, execution, frame, action) -> None:
    frame.pc = frame.blocks.end[frame.blocks.loop[frame.pc]]


def _wait(engine, ctx, execution, frame, action) -> None:
    seconds = engine.values.to_number(ctx.eval(action.args[0])) if action.args else 0.0
    behavior = action.args[1] if len(action.args) > 1 else "Ignore Condition"
    if behavior not in WAIT_BEHAVIORS:
        raise WorkshopError(f"unknown wait behaviour {behavior!r}")
    milliseconds = (
        max(MIN_WAIT_MS, round(min(seconds, 1.0e8) * 1000)) if math.isfinite(seconds) else MIN_WAIT_MS
    )
    holds = engine.conditions(execution) if behavior == "Restart When True" else True
    execution.wait = Wait(engine.now + milliseconds, behavior, was_true=holds)
    frame.pc += 1


def _wait_until(engine, ctx, execution, frame, action) -> None:
    frame.pc += 1
    if _truth(ctx, action):
        return
    seconds = engine.values.to_number(ctx.eval(action.args[1])) if len(action.args) > 1 else 0.0
    milliseconds = max(MIN_WAIT_MS, round(min(seconds, 1.0e8) * 1000))
    execution.wait = Wait(engine.now + milliseconds, condition=action.args[0])


def _abort(engine, ctx, execution, frame, action) -> None:
    """Abort and its variants end the whole rule, also from inside a called subroutine (assumption)."""
    name = action.name
    if (
        name == "Abort"
        or (name == "Abort If" and _truth(ctx, action))
        or (name == "Abort If Condition Is True" and engine.conditions(execution))
        or (name == "Abort If Condition Is False" and not engine.conditions(execution))
    ):
        execution.finished = True
    else:
        frame.pc += 1


def _loop(engine, ctx, execution, frame, action) -> None:
    """Loop and its variants go back to the first action of the current action list."""
    name = action.name
    if (
        name == "Loop"
        or (name == "Loop If" and _truth(ctx, action))
        or (name == "Loop If Condition Is True" and engine.conditions(execution))
        or (name == "Loop If Condition Is False" and not engine.conditions(execution))
    ):
        frame.pc = 0
    else:
        frame.pc += 1


def _skip(engine, ctx, execution, frame, action) -> None:
    if action.name == "Skip":
        count = engine.values.to_number(ctx.eval(action.args[0])) if action.args else 0
    else:
        count = engine.values.to_number(ctx.eval(action.args[1])) if _truth(ctx, action) else 0
    frame.pc += 1 + max(0, int(count))


def _call(engine, ctx, execution, frame, action) -> None:
    rule = engine._subroutine(action.args[0])
    if len(execution.frames) > 64:
        raise WorkshopError("subroutine calls nested more than 64 deep")
    execution.frames.append(Frame(rule.actions, engine.blocks[rule]))


def _start_rule(engine, ctx, execution, frame, action) -> None:
    behavior = action.args[1] if len(action.args) > 1 else "Restart Rule"
    engine.start_rule(action.args[0], execution, behavior == "Restart Rule")
    frame.pc += 1


FLOW = {
    "If": _if,
    "Else If": _branch_end,
    "Else": _branch_end,
    "While": _while,
    "End": _end,
    "For Global Variable": _for,
    "For Player Variable": _for,
    "Break": _break,
    "Continue": _continue_loop,
    "Wait": _wait,
    "Wait Until": _wait_until,
    "Abort": _abort,
    "Abort If": _abort,
    "Abort If Condition Is True": _abort,
    "Abort If Condition Is False": _abort,
    "Loop": _loop,
    "Loop If": _loop,
    "Loop If Condition Is True": _loop,
    "Loop If Condition Is False": _loop,
    "Skip": _skip,
    "Skip If": _skip,
    "Call Subroutine": _call,
    "Start Rule": _start_rule,
}


# --- variables and the inspector -----------------------------------------------------------------


def _global(engine, action, position: int = 0) -> tuple:
    return ("global", engine.global_index(action.args[position]))


def _player(engine, ctx, action) -> list[tuple]:
    """Player variable actions apply to each player of their first parameter."""
    players = engine.values.players_of(ctx.eval(action.args[0]))
    index = engine.player_index(action.args[1])
    return [("player", player.id, index) for player in players]


def _set(engine, ctx, action) -> None:
    if action.name == "Set Global Variable":
        engine.write(_global(engine, action), ctx.eval(action.args[1]))
        return
    value = ctx.eval(action.args[2])
    for target in _player(engine, ctx, action):
        engine.write(target, value)


def _set_at_index(engine, ctx, action) -> None:
    if action.name == "Set Global Variable At Index":
        targets, index, value = [_global(engine, action)], action.args[1], action.args[2]
    else:
        targets, index, value = _player(engine, ctx, action), action.args[2], action.args[3]
    position, value = engine.values.to_index(ctx.eval(index)), ctx.eval(value)
    for target in targets:
        engine.write(target, engine.values.set_at(engine.read(target), position, value))


def _modify(engine, ctx, action) -> None:
    if action.name == "Modify Global Variable":
        targets, operation, operand = [_global(engine, action)], action.args[1], action.args[2]
    else:
        targets, operation, operand = _player(engine, ctx, action), action.args[2], action.args[3]
    value = ctx.eval(operand)
    for target in targets:
        engine.write(target, engine.values.modify(ctx, engine.read(target), operation, value))


def _modify_at_index(engine, ctx, action) -> None:
    if action.name == "Modify Global Variable At Index":
        targets, rest = [_global(engine, action)], action.args[1:]
    else:
        targets, rest = _player(engine, ctx, action), action.args[2:]
    position, operation, value = engine.values.to_index(ctx.eval(rest[0])), rest[1], ctx.eval(rest[2])
    for target in targets:
        current = engine.read(target)
        element = engine.values.value_at(current, position)
        engine.write(
            target,
            engine.values.set_at(current, position, engine.values.modify(ctx, element, operation, value)),
        )


def _chase(engine, ctx, action) -> None:
    over_time = action.name.endswith("Over Time")
    if action.name.startswith("Chase Global"):
        targets, rest = [_global(engine, action)], action.args[1:]
    else:
        targets, rest = _player(engine, ctx, action), action.args[2:]
    reevaluate = len(rest) > 2 and rest[2] not in ("None",)
    for target in targets:
        engine.chase(target, rest[0], rest[1], over_time, reevaluate, ctx.execution)


def _stop_chase(engine, ctx, action) -> None:
    targets = (
        [_global(engine, action)]
        if action.name == "Stop Chasing Global Variable"
        else _player(engine, ctx, action)
    )
    for target in targets:
        engine.stop_chase(target)


def _log(engine, ctx, action) -> None:
    text = engine.values.to_text(ctx, ctx.eval(action.args[0])) if action.args else ""
    engine.log.append(text)
    engine.world.log(text)


NATIVE = {
    "Set Global Variable": _set,
    "Set Player Variable": _set,
    "Set Global Variable At Index": _set_at_index,
    "Set Player Variable At Index": _set_at_index,
    "Modify Global Variable": _modify,
    "Modify Player Variable": _modify,
    "Modify Global Variable At Index": _modify_at_index,
    "Modify Player Variable At Index": _modify_at_index,
    "Chase Global Variable Over Time": _chase,
    "Chase Player Variable Over Time": _chase,
    "Chase Global Variable At Rate": _chase,
    "Chase Player Variable At Rate": _chase,
    "Stop Chasing Global Variable": _stop_chase,
    "Stop Chasing Player Variable": _stop_chase,
    "Log To Inspector": _log,
}
