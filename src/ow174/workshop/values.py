"""Workshop values: what each of the catalog's 267 values computes, by catalog name.

Values that need nothing but their parameters (numbers, vectors, logic, arrays, text, variables, event
values) are computed here. Values about players are computed from a few World questions (the players,
their team, slot, hero, position, facing and whether they are alive) where the in-game description says
how; every other value about the game (health, scores, objectives, statuses, buttons, ray casts) is asked
of the World by name through World.query, so a world implements exactly what it can answer.

The rules come from the values' in-game descriptions, the Workshop's public documentation and the client's
own value model where they share it (equality within 1.1920929e-5, an unset variable is 0 and equal to
null). Choices the descriptions leave open are listed in docs/WORKSHOP_ENGINE.txt.
"""

import math
from dataclasses import dataclass

from ow174.game.script.expr import EPSILON, Entity, Vec3, equal
from ow174.workshop.engine import (
    MAX_STEPS,
    MODIFY_OPERATIONS,
    OPERATORS,
    Unsupported,
    Value,
    WorkshopError,
)

# --- constants of the game ---------------------------------------------------------------------


@dataclass(frozen=True)
class Hero:
    name: str


@dataclass(frozen=True)
class Team:
    name: str  # "All Teams", "Team 1" or "Team 2"


@dataclass(frozen=True)
class Button:
    name: str


@dataclass(frozen=True)
class GameMap:
    name: str


@dataclass(frozen=True)
class GameMode:
    name: str


@dataclass(frozen=True)
class Color:
    name: str = ""
    rgba: tuple = ()


ALL_TEAMS, TEAM_1, TEAM_2 = Team("All Teams"), Team("Team 1"), Team("Team 2")
# The 32 heroes of build 104319 by role, in the game's own hero order.
TANKS = ("Reinhardt", "Winston", "Roadhog", "Zarya", "D.Va", "Orisa", "Wrecking Ball", "Sigma")
DAMAGE = (
    "Reaper",
    "Tracer",
    "Hanzo",
    "Torbjörn",
    "Pharah",
    "Widowmaker",
    "Bastion",
    "Symmetra",
    "Genji",
    "Cassidy",
    "Junkrat",
    "Soldier: 76",
    "Mei",
    "Sombra",
    "Doomfist",
    "Ashe",
    "Echo",
)
SUPPORT = ("Mercy", "Zenyatta", "Lúcio", "Ana", "Brigitte", "Moira", "Baptiste")
HERO_ORDER = (
    "Reaper",
    "Tracer",
    "Mercy",
    "Hanzo",
    "Torbjörn",
    "Reinhardt",
    "Pharah",
    "Winston",
    "Widowmaker",
    "Bastion",
    "Symmetra",
    "Zenyatta",
    "Genji",
    "Roadhog",
    "Cassidy",
    "Junkrat",
    "Zarya",
    "Soldier: 76",
    "Lúcio",
    "D.Va",
    "Mei",
    "Sombra",
    "Doomfist",
    "Ana",
    "Orisa",
    "Brigitte",
    "Moira",
    "Wrecking Ball",
    "Ashe",
    "Echo",
    "Baptiste",
    "Sigma",
)
DIRECTIONS = {
    "Left": Vec3(1.0, 0.0, 0.0),
    "Right": Vec3(-1.0, 0.0, 0.0),
    "Up": Vec3(0.0, 1.0, 0.0),
    "Down": Vec3(0.0, -1.0, 0.0),
    "Forward": Vec3(0.0, 0.0, 1.0),
    "Backward": Vec3(0.0, 0.0, -1.0),
}
ZERO = Vec3(0.0, 0.0, 0.0)


def team(name: str) -> Value:
    return Value("Team", (name,))


def text(value: str, *args) -> Value:
    return Value("Custom String", (value, *args))


# --- conversions -------------------------------------------------------------------------------


def to_number(value) -> float:
    """A number: null 0, true 1, false 0, an array its first element, anything else 0."""
    if value is None:
        return 0.0
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, tuple):
        return to_number(value[0]) if value else 0.0
    return 0.0


def truthy(value) -> bool:
    """Null, false, 0, the zero vector and an empty array are false; an array is its first element."""
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, Vec3):
        return any(axis != 0 for axis in value)
    if isinstance(value, tuple):
        return truthy(value[0]) if value else False
    if isinstance(value, str):
        return value != ""
    return True


def entity_of(value) -> Entity | None:
    if isinstance(value, Entity):
        return value
    if isinstance(value, tuple):
        for item in value:
            if isinstance(item, Entity):
                return item
    return None


def players_of(value) -> list[Entity]:
    """The players a player parameter names: one player, or each player of an array."""
    if isinstance(value, Entity):
        return [value]
    if isinstance(value, tuple):
        return [item for item in value if isinstance(item, Entity)]
    return []


def to_index(value) -> int:
    return int(to_number(value))


def as_array(value) -> tuple:
    """An array as itself; null as the empty array; any other value as a one-element array."""
    if isinstance(value, tuple):
        return value
    return () if value is None else (value,)


def vector_of(ctx, value) -> Vec3:
    """A vector: a player is their position, an array its first element, anything else the zero vector."""
    if isinstance(value, Vec3):
        return value
    if isinstance(value, Entity):
        return ctx.world.position(value) or ZERO
    if isinstance(value, tuple):
        return vector_of(ctx, value[0]) if value else ZERO
    return ZERO


def _team_of(value) -> Team:
    if isinstance(value, Team):
        return value
    return ALL_TEAMS if value is None else Team(str(value))


def _hero_name(value) -> str | None:
    if isinstance(value, Hero):
        return value.name
    return value if isinstance(value, str) else None


def length(vector: Vec3) -> float:
    return math.sqrt(vector.x * vector.x + vector.y * vector.y + vector.z * vector.z)


def _vec(operation, a: Vec3, b: Vec3) -> Vec3:
    return Vec3(operation(a.x, b.x), operation(a.y, b.y), operation(a.z, b.z))


def _is_vectorish(value) -> bool:
    return isinstance(value, (Vec3, Entity)) or (
        isinstance(value, tuple) and bool(value) and isinstance(value[0], (Vec3, Entity))
    )


def compare(ctx, left, op: str, right) -> bool:
    if op == "==":
        return values_equal(left, right)
    if op == "!=":
        return not values_equal(left, right)
    if op not in OPERATORS:
        raise WorkshopError(f"unknown comparison {op!r}")
    a, b = to_number(left), to_number(right)
    return {"<": a < b - EPSILON, "<=": a - EPSILON <= b, ">": a > b + EPSILON, ">=": a + EPSILON >= b}[op]


def values_equal(a, b) -> bool:
    """Equality of the client's value model, extended to the Workshop's own constants."""
    if isinstance(a, (Hero, Team, Button, GameMap, GameMode, Color, str)) or isinstance(
        b, (Hero, Team, Button, GameMap, GameMode, Color, str)
    ):
        return a == b
    if isinstance(a, tuple) and isinstance(b, tuple):
        return len(a) == len(b) and all(values_equal(x, y) for x, y in zip(a, b, strict=True))
    if isinstance(a, bool) or isinstance(b, bool):
        return truthy(a) == truthy(b)
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) <= EPSILON
    return equal(a, b)


# --- evaluation --------------------------------------------------------------------------------


class Context:
    """Where a value is evaluated: the engine, the running rule and its event."""

    def __init__(self, engine, execution) -> None:
        self.engine = engine
        self.execution = execution

    @property
    def world(self):
        return self.engine.world

    @property
    def event(self):
        return self.execution.event

    def eval(self, arg):
        return evaluate(self, arg) if isinstance(arg, Value) else arg

    truthy = staticmethod(truthy)


VALUES: dict[str, tuple] = {}  # name -> (function, lazy)


def value(*names: str, lazy: bool = False):
    """Register a value function. An eager one gets its parameters evaluated, a lazy one gets them
    as written (to evaluate per array element, or only one branch)."""

    def register(function):
        for name in names:
            VALUES[name] = (function, lazy)
        return function

    return register


def evaluate(ctx: Context, item: Value):
    entry = VALUES.get(item.name)
    if entry is not None:
        function, lazy = entry
        return function(ctx, *item.args) if lazy else function(ctx, *(ctx.eval(arg) for arg in item.args))
    return ctx.world.query(item.name, tuple(ctx.eval(arg) for arg in item.args), ctx)


def _arg(args: tuple, index: int, default=None):
    return args[index] if index < len(args) else default


# --- constants and logic -----------------------------------------------------------------------


@value("Number")
def _number(ctx, literal=0.0):
    return float(literal)


@value("True")
def _true(ctx):
    return True


@value("False")
def _false(ctx):
    return False


@value("Null")
def _null(ctx):
    return None


@value("Hero")
def _hero(ctx, name):
    return Hero(name) if isinstance(name, str) else name


@value("Team")
def _team(ctx, name="All Teams"):
    return _team_of(name)


@value("Button")
def _button(ctx, name):
    return Button(name) if isinstance(name, str) else name


@value("Map")
def _map(ctx, name):
    return GameMap(name) if isinstance(name, str) else name


@value("Game Mode")
def _game_mode(ctx, name):
    return GameMode(name) if isinstance(name, str) else name


@value("Color")
def _color(ctx, name):
    return Color(name) if isinstance(name, str) else name


@value("Custom Color")
def _custom_color(ctx, red=0, green=0, blue=0, alpha=255):
    return Color("", tuple(max(0.0, min(255.0, to_number(item))) for item in (red, green, blue, alpha)))


@value("Vector")
def _vector(ctx, x=0.0, y=0.0, z=0.0):
    return Vec3(to_number(x), to_number(y), to_number(z))


for _name, _direction in DIRECTIONS.items():
    VALUES[_name] = ((lambda ctx, _d=_direction: _d), False)


@value("And")
def _and(ctx, a, b):
    return truthy(a) and truthy(b)


@value("Or")
def _or(ctx, a, b):
    return truthy(a) or truthy(b)


@value("Not")
def _not(ctx, a):
    return not truthy(a)


@value("Compare")
def _compare(ctx, left, op, right):
    return compare(ctx, left, op, right)


@value("If-Then-Else", lazy=True)
def _if_then_else(ctx, condition, then, otherwise=None):
    return ctx.eval(then) if truthy(ctx.eval(condition)) else ctx.eval(otherwise)


@value("Evaluate Once", "Update Every Frame")
def _passthrough(ctx, *args):
    return args[-1] if args else None


# --- variables and the event ---------------------------------------------------------------------


@value("Global Variable")
def _global_variable(ctx, reference):
    return ctx.engine.globals[ctx.engine.global_index(reference)]


@value("Player Variable")
def _player_variable(ctx, player, reference):
    entity = entity_of(player)
    if entity is None:
        return 0
    return ctx.engine.player_vars.get(entity.id, [0] * 128)[ctx.engine.player_index(reference)]


@value("Event Player")
def _event_player(ctx):
    return ctx.event.player


EVENT_VALUES = {
    "Attacker": None,
    "Victim": None,
    "Healer": None,
    "Healee": None,
    "Event Damage": 0.0,
    "Event Healing": 0.0,
    "Event Was Critical Hit": False,
    "Event Direction": ZERO,
    "Event Ability": None,
    "Event Was Health Pack": False,
    "Event Was Environment": False,
}
for _name, _default in EVENT_VALUES.items():
    VALUES[_name] = ((lambda ctx, _n=_name, _v=_default: ctx.event.value(_n, _v)), False)


@value("Total Time Elapsed")
def _total_time(ctx):
    return ctx.engine.now / 1000.0


# --- numbers -----------------------------------------------------------------------------------


def _arith(ctx, operation: str, a, b):
    if operation in ("Add", "Subtract") and (_is_vectorish(a) or _is_vectorish(b)):
        va = vector_of(ctx, a) if _is_vectorish(a) else Vec3(*(to_number(a),) * 3)
        vb = vector_of(ctx, b) if _is_vectorish(b) else Vec3(*(to_number(b),) * 3)
        return _vec((lambda x, y: x + y) if operation == "Add" else (lambda x, y: x - y), va, vb)
    if operation in ("Multiply", "Divide") and (isinstance(a, Vec3) or isinstance(b, Vec3)):
        va = a if isinstance(a, Vec3) else Vec3(*(to_number(a),) * 3)
        vb = b if isinstance(b, Vec3) else Vec3(*(to_number(b),) * 3)
        if operation == "Multiply":
            return _vec(lambda x, y: x * y, va, vb)
        return _vec(lambda x, y: x / y if y != 0 else 0.0, va, vb)
    x, y = to_number(a), to_number(b)
    if operation == "Add":
        return x + y
    if operation == "Subtract":
        return x - y
    if operation == "Multiply":
        return x * y
    if operation == "Divide":
        return x / y if y != 0 else 0.0
    if operation == "Modulo":
        return math.fmod(x, y) if y != 0 else 0.0
    if operation == "Raise To Power":
        try:
            result = math.pow(x, y)
        except (OverflowError, ValueError):
            return 0.0
        return result if math.isfinite(result) else 0.0
    if operation == "Min":
        return min(x, y)
    if operation == "Max":
        return max(x, y)
    raise WorkshopError(f"unknown operation {operation!r}")


for _operation in ("Add", "Subtract", "Multiply", "Divide", "Modulo", "Raise To Power", "Min", "Max"):
    VALUES[_operation] = ((lambda ctx, a=0, b=0, _o=_operation: _arith(ctx, _o, a, b)), False)


@value(" ")
def _operation_value(ctx, a, operation, b):
    """The catalog's unnamed value: the operation its dropdown names, the same set Modify Variable has."""
    return modify(ctx, a, operation, b)


@value("Absolute Value")
def _abs(ctx, x):
    return abs(to_number(x))


@value("Square Root")
def _sqrt(ctx, x):
    x = to_number(x)
    return math.sqrt(x) if x > 0 else 0.0


@value("Round To Integer")
def _round(ctx, x, mode="To Nearest"):
    x = to_number(x)
    if mode == "Up":
        return float(math.ceil(x))
    if mode == "Down":
        return float(math.floor(x))
    return float(math.floor(x + 0.5) if x >= 0 else math.ceil(x - 0.5))


def _clamp_unit(x: float) -> float:
    return max(-1.0, min(1.0, x))


TRIG = {
    "Sine From Degrees": lambda x: math.sin(math.radians(x)),
    "Cosine From Degrees": lambda x: math.cos(math.radians(x)),
    "Tangent From Degrees": lambda x: math.tan(math.radians(x)),
    "Sine From Radians": math.sin,
    "Cosine From Radians": math.cos,
    "Tangent From Radians": math.tan,
    "Arcsine In Degrees": lambda x: math.degrees(math.asin(_clamp_unit(x))),
    "Arcsine In Radians": lambda x: math.asin(_clamp_unit(x)),
    "Arccosine In Degrees": lambda x: math.degrees(math.acos(_clamp_unit(x))),
    "Arccosine In Radians": lambda x: math.acos(_clamp_unit(x)),
}
for _name, _function in TRIG.items():
    VALUES[_name] = ((lambda ctx, x=0, _f=_function: _f(to_number(x))), False)


@value("Arctangent In Radians")
def _atan(ctx, numerator, denominator):
    return math.atan2(to_number(numerator), to_number(denominator))


@value("Arctangent In Degrees")
def _atan_degrees(ctx, numerator, denominator):
    return math.degrees(_atan(ctx, numerator, denominator))


@value("Angle Difference")
def _angle_difference(ctx, a, b):
    """The signed difference from a to b in degrees, between -180 and 180."""
    return math.remainder(to_number(b) - to_number(a), 360.0)


@value("Random Integer")
def _random_integer(ctx, low, high):
    low, high = sorted((math.floor(to_number(low)), math.floor(to_number(high))))
    return float(ctx.world.rng.randint(low, high))


@value("Random Real")
def _random_real(ctx, low, high):
    return ctx.world.rng.uniform(to_number(low), to_number(high))


# --- vectors -----------------------------------------------------------------------------------


@value("X Component Of")
def _x(ctx, v):
    return vector_of(ctx, v).x


@value("Y Component Of")
def _y(ctx, v):
    return vector_of(ctx, v).y


@value("Z Component Of")
def _z(ctx, v):
    return vector_of(ctx, v).z


@value("Distance Between")
def _distance(ctx, a, b):
    return length(_vec(lambda x, y: x - y, vector_of(ctx, b), vector_of(ctx, a)))


@value("Vector Towards")
def _vector_towards(ctx, a, b):
    return _vec(lambda x, y: x - y, vector_of(ctx, b), vector_of(ctx, a))


def normalize(v: Vec3) -> Vec3:
    size = length(v)
    return Vec3(v.x / size, v.y / size, v.z / size) if size > 0 else ZERO


@value("Direction Towards")
def _direction_towards(ctx, a, b):
    return normalize(_vector_towards(ctx, a, b))


@value("Normalize")
def _normalize(ctx, v):
    return normalize(vector_of(ctx, v))


@value("Magnitude Of")
def _magnitude(ctx, v):
    return length(vector_of(ctx, v))


@value("Dot Product")
def _dot(ctx, a, b):
    a, b = vector_of(ctx, a), vector_of(ctx, b)
    return a.x * b.x + a.y * b.y + a.z * b.z


@value("Cross Product")
def _cross(ctx, a, b):
    a, b = vector_of(ctx, a), vector_of(ctx, b)
    return Vec3(a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x)


@value("Angle Between Vectors")
def _angle_between(ctx, a, b):
    a, b = vector_of(ctx, a), vector_of(ctx, b)
    size = length(a) * length(b)
    if size == 0:
        return 0.0
    return math.degrees(math.acos(_clamp_unit((a.x * b.x + a.y * b.y + a.z * b.z) / size)))


def direction_from_angles(horizontal: float, vertical: float) -> Vec3:
    """Horizontal 0 faces forward (+Z) and 90 faces left (+X); vertical 90 faces straight down."""
    h, v = math.radians(horizontal), math.radians(vertical)
    return Vec3(math.sin(h) * math.cos(v), -math.sin(v), math.cos(h) * math.cos(v))


@value("Direction From Angles")
def _direction_from_angles(ctx, horizontal, vertical):
    return direction_from_angles(to_number(horizontal), to_number(vertical))


def horizontal_angle(v: Vec3) -> float:
    return math.degrees(math.atan2(v.x, v.z)) if (v.x or v.z) else 0.0


def vertical_angle(v: Vec3) -> float:
    size = length(v)
    return -math.degrees(math.asin(_clamp_unit(v.y / size))) if size > 0 else 0.0


@value("Horizontal Angle From Direction")
def _horizontal_from_direction(ctx, v):
    return horizontal_angle(vector_of(ctx, v))


@value("Vertical Angle From Direction")
def _vertical_from_direction(ctx, v):
    return vertical_angle(vector_of(ctx, v))


def _facing(ctx, player) -> Vec3:
    entity = entity_of(player)
    return (ctx.world.facing(entity) if entity is not None else None) or DIRECTIONS["Forward"]


def _frame(ctx, player):
    """The player's left, up and forward axes from their horizontal facing."""
    h = math.radians(horizontal_angle(_facing(ctx, player)))
    forward = Vec3(math.sin(h), 0.0, math.cos(h))
    left = Vec3(math.cos(h), 0.0, -math.sin(h))
    return left, DIRECTIONS["Up"], forward


@value("World Vector Of")
def _world_vector(ctx, local, player, transformation="Rotation"):
    local = vector_of(ctx, local)
    left, up, forward = _frame(ctx, player)
    result = Vec3(
        *(local.x * a + local.y * b + local.z * c for a, b, c in zip(left, up, forward, strict=True))
    )
    if transformation == "Rotation And Translation":
        result = _vec(lambda x, y: x + y, result, vector_of(ctx, entity_of(player)))
    return result


@value("Local Vector Of")
def _local_vector(ctx, world_vector, player, transformation="Rotation"):
    world_vector = vector_of(ctx, world_vector)
    if transformation == "Rotation And Translation":
        world_vector = _vec(lambda x, y: x - y, world_vector, vector_of(ctx, entity_of(player)))
    left, up, forward = _frame(ctx, player)
    return Vec3(
        *(sum(a * b for a, b in zip(world_vector, axis, strict=True)) for axis in (left, up, forward))
    )


# --- arrays ------------------------------------------------------------------------------------


@value("Empty Array")
def _empty(ctx):
    return ()


@value("Array")
def _array(ctx, *items):
    return tuple(items)


@value("Count Of")
def _count(ctx, items):
    return float(len(items)) if isinstance(items, tuple) else 0.0


def value_at(items, index: int):
    items = as_array(items) if not isinstance(items, tuple) and items not in (0, 0.0) else items
    if isinstance(items, tuple) and 0 <= index < len(items):
        return items[index]
    return 0


def set_at(items, index: int, item):
    """The array with `item` at `index`, grown with zeros. A number other than 0 starts the array."""
    base = list(items) if isinstance(items, tuple) else ([] if items in (None, 0, 0.0) else [items])
    if index < 0:
        return tuple(base)
    base.extend([0] * (index + 1 - len(base)))
    base[index] = item
    return tuple(base)


@value("Value In Array")
def _value_in_array(ctx, items, index):
    return value_at(items, to_index(index))


@value("First Of")
def _first(ctx, items):
    items = as_array(items)
    return items[0] if items else None


@value("Last Of")
def _last(ctx, items):
    items = as_array(items)
    return items[-1] if items else None


@value("Array Slice")
def _slice(ctx, items, start, count):
    items, start, count = as_array(items), max(0, to_index(start)), max(0, to_index(count))
    return items[start : start + count]


@value("Append To Array")
def _append(ctx, items, more):
    return as_array(items) + as_array(more)


@value("Remove From Array")
def _remove(ctx, items, removed):
    removed = as_array(removed)
    return tuple(item for item in as_array(items) if not any(values_equal(item, other) for other in removed))


@value("Array Contains")
def _contains(ctx, items, item):
    return any(values_equal(element, item) for element in as_array(items))


@value("Index Of Array Value")
def _index_of(ctx, items, item):
    for index, element in enumerate(as_array(items)):
        if values_equal(element, item):
            return float(index)
    return -1.0


@value("Random Value In Array")
def _random_value(ctx, items):
    items = as_array(items)
    return ctx.world.rng.choice(items) if items else None


@value("Randomized Array")
def _randomized(ctx, items):
    items = list(as_array(items))
    ctx.world.rng.shuffle(items)
    return tuple(items)


def _each(ctx, items, expression):
    """(element, the expression evaluated with that element as Current Array Element), in order."""
    current = ctx.execution.current
    for index, element in enumerate(as_array(ctx.eval(items))):
        current.append((element, float(index)))
        try:
            yield element, ctx.eval(expression)
        finally:
            current.pop()


@value("Current Array Element")
def _current_element(ctx):
    return ctx.execution.current[-1][0] if ctx.execution.current else None


@value("Current Array Index")
def _current_index(ctx):
    return ctx.execution.current[-1][1] if ctx.execution.current else 0.0


@value("Filtered Array", lazy=True)
def _filtered(ctx, items, condition):
    return tuple(element for element, keep in _each(ctx, items, condition) if truthy(keep))


@value("Sorted Array", lazy=True)
def _sorted(ctx, items, rank):
    ranked = list(_each(ctx, items, rank))
    return tuple(element for element, _ in sorted(ranked, key=lambda pair: to_number(pair[1])))


@value("Mapped Array", lazy=True)
def _mapped(ctx, items, mapping):
    return tuple(result for _, result in _each(ctx, items, mapping))


@value("Is True For All", lazy=True)
def _all(ctx, items, condition):
    return all(truthy(result) for _, result in _each(ctx, items, condition))


@value("Is True For Any", lazy=True)
def _any(ctx, items, condition):
    return any(truthy(result) for _, result in _each(ctx, items, condition))


# --- text --------------------------------------------------------------------------------------


def format_number(x: float) -> str:
    if x == int(x) and abs(x) < 1e15:
        return str(int(x))
    return f"{x:.2f}".rstrip("0").rstrip(".")


def to_text(ctx, item) -> str:
    if item is None:
        return "null"
    if isinstance(item, bool):
        return "True" if item else "False"
    if isinstance(item, (int, float)):
        return format_number(float(item))
    if isinstance(item, str):
        return item
    if isinstance(item, Vec3):
        return "(" + ", ".join(f"{axis:.2f}" for axis in item) + ")"
    if isinstance(item, Entity):
        return ctx.world.name_of(item)
    if isinstance(item, tuple):
        return ", ".join(to_text(ctx, element) for element in item)
    if isinstance(item, Color) and not item.name:
        return "Custom Color"
    return getattr(item, "name", str(item))


@value("Custom String", "String")
def _custom_string(ctx, pattern="", *args):
    """{0}, {1} and {2} are replaced by the text of the values that follow."""
    result = str(pattern)
    for index in range(3):
        result = result.replace("{" + str(index) + "}", to_text(ctx, _arg(args, index)))
    return result


@value("String Contains")
def _string_contains(ctx, haystack, needle):
    return to_text(ctx, needle) in to_text(ctx, haystack)


@value("String Length")
def _string_length(ctx, item):
    return float(len(to_text(ctx, item)))


@value("String Slice")
def _string_slice(ctx, item, start, count):
    start, count = max(0, to_index(start)), max(0, to_index(count))
    return to_text(ctx, item)[start : start + count]


@value("Char In String")
def _char(ctx, item, index):
    item, index = to_text(ctx, item), to_index(index)
    return item[index] if 0 <= index < len(item) else ""


@value("Index Of String Char")
def _index_of_char(ctx, item, char):
    return float(to_text(ctx, item).find(to_text(ctx, char)))


@value("String Split")
def _split(ctx, item, separator):
    separator = to_text(ctx, separator)
    return tuple(to_text(ctx, item).split(separator)) if separator else tuple(to_text(ctx, item))


@value("String Replace")
def _replace(ctx, item, old, new):
    old = to_text(ctx, old)
    return to_text(ctx, item).replace(old, to_text(ctx, new)) if old else to_text(ctx, item)


# --- teams and heroes --------------------------------------------------------------------------


@value("Opposite Team Of")
def _opposite(ctx, item):
    item = _team_of(item)
    return {TEAM_1: TEAM_2, TEAM_2: TEAM_1}.get(item, ALL_TEAMS)


@value("All Heroes")
def _all_heroes(ctx):
    return tuple(Hero(name) for name in HERO_ORDER)


@value("All Tank Heroes")
def _tanks(ctx):
    return tuple(Hero(name) for name in HERO_ORDER if name in TANKS)


@value("All Damage Heroes")
def _damage(ctx):
    return tuple(Hero(name) for name in HERO_ORDER if name in DAMAGE)


@value("All Support Heroes")
def _support(ctx):
    return tuple(Hero(name) for name in HERO_ORDER if name in SUPPORT)


# --- players: from the World's basic questions -------------------------------------------------


def _on_team(ctx, player: Entity, item) -> bool:
    item = _team_of(item)
    return item == ALL_TEAMS or ctx.world.team_of(player) == item.name


def _players(ctx, team_value=None, alive=None) -> tuple:
    result = []
    for player in ctx.world.players():
        if not _on_team(ctx, player, team_value):
            continue
        if alive is not None and bool(ctx.world.is_alive(player)) != alive:
            continue
        result.append(player)
    return tuple(result)


@value("All Players")
def _all_players(ctx, team_value=None):
    return _players(ctx, team_value)


@value("All Living Players")
def _living(ctx, team_value=None):
    return _players(ctx, team_value, alive=True)


@value("All Dead Players")
def _dead(ctx, team_value=None):
    return _players(ctx, team_value, alive=False)


@value("Number Of Players")
def _count_players(ctx, team_value=None):
    return float(len(_players(ctx, team_value)))


@value("Number Of Living Players")
def _count_living(ctx, team_value=None):
    return float(len(_players(ctx, team_value, alive=True)))


@value("Number Of Dead Players")
def _count_dead(ctx, team_value=None):
    return float(len(_players(ctx, team_value, alive=False)))


def _plays(ctx, player: Entity, hero) -> bool:
    current = ctx.world.hero_of(player)
    return current is not None and _hero_name(current) == _hero_name(hero)


@value("Players On Hero")
def _players_on_hero(ctx, hero, team_value=None):
    return tuple(player for player in _players(ctx, team_value) if _plays(ctx, player, hero))


@value("Number Of Heroes")
def _number_of_heroes(ctx, hero, team_value=None):
    return float(len(_players_on_hero(ctx, hero, team_value)))


@value("Is Hero Being Played")
def _is_hero_played(ctx, hero, team_value=None):
    return bool(_players_on_hero(ctx, hero, team_value))


@value("Players In Slot")
def _players_in_slot(ctx, slot, team_value=None):
    slot = to_index(slot)
    found = tuple(player for player in _players(ctx, team_value) if ctx.world.slot_of(player) == slot)
    if _team_of(team_value) == ALL_TEAMS:
        return found
    return found[0] if found else None


@value("Team Of")
def _team_of_player(ctx, player):
    entity = entity_of(player)
    return Team(ctx.world.team_of(entity)) if entity is not None else ALL_TEAMS


@value("Slot Of")
def _slot_of(ctx, player):
    entity = entity_of(player)
    return float(ctx.world.slot_of(entity)) if entity is not None else -1.0


@value("Hero Of")
def _hero_of(ctx, player):
    entity = entity_of(player)
    hero = ctx.world.hero_of(entity) if entity is not None else None
    return Hero(hero) if isinstance(hero, str) else hero


@value("Is Alive")
def _is_alive(ctx, player):
    entity = entity_of(player)
    return entity is not None and bool(ctx.world.is_alive(entity))


@value("Is Dead")
def _is_dead(ctx, player):
    entity = entity_of(player)
    return entity is not None and not ctx.world.is_alive(entity)


@value("Position Of")
def _position(ctx, player):
    entity = entity_of(player)
    return (ctx.world.position(entity) if entity is not None else None) or ZERO


@value("Facing Direction Of")
def _facing_direction(ctx, player):
    return _facing(ctx, player)


@value("Horizontal Facing Angle Of")
def _horizontal_facing(ctx, player):
    return horizontal_angle(_facing(ctx, player))


@value("Vertical Facing Angle Of")
def _vertical_facing(ctx, player):
    return vertical_angle(_facing(ctx, player))


@value("Horizontal Angle Towards")
def _horizontal_towards(ctx, player, location):
    direction = _vector_towards(ctx, _position(ctx, player), location)
    return math.remainder(horizontal_angle(direction) - horizontal_angle(_facing(ctx, player)), 360.0)


@value("Vertical Angle Towards")
def _vertical_towards(ctx, player, location):
    direction = _vector_towards(
        ctx, ctx.world.eye_position(entity_of(player)) or _position(ctx, player), location
    )
    return vertical_angle(direction) - vertical_angle(_facing(ctx, player))


@value("Is In View Angle")
def _in_view(ctx, player, location, angle):
    """Whether the location lies within half the view angle of the player's facing direction."""
    eye = ctx.world.eye_position(entity_of(player)) or _position(ctx, player)
    direction = _vector_towards(ctx, eye, location)
    return _angle_between(ctx, _facing(ctx, player), direction) <= to_number(angle) / 2.0 + EPSILON


@value("Players in View Angle")
def _players_in_view(ctx, player, team_value, angle):
    viewer = entity_of(player)
    return tuple(
        other
        for other in _players(ctx, team_value, alive=True)
        if other != viewer and _in_view(ctx, viewer, other, angle)
    )


def _by_distance(ctx, location, team_value) -> list[tuple[float, Entity]]:
    location = vector_of(ctx, location)
    return sorted(
        ((_distance(ctx, location, player), player) for player in _players(ctx, team_value, True)),
        key=lambda pair: pair[0],
    )


@value("Closest Player To")
def _closest(ctx, location, team_value=None):
    ranked = _by_distance(ctx, location, team_value)
    return ranked[0][1] if ranked else None


@value("Farthest Player From")
def _farthest(ctx, location, team_value=None):
    ranked = _by_distance(ctx, location, team_value)
    return ranked[-1][1] if ranked else None


@value("Players Within Radius")
def _within(ctx, location, radius, team_value=None, line_of_sight="Off"):
    center, radius = vector_of(ctx, location), to_number(radius)
    found = []
    for distance, player in _by_distance(ctx, center, team_value):
        if distance > radius:
            break
        if line_of_sight != "Off" and not ctx.world.line_of_sight(
            center, _position(ctx, player), line_of_sight
        ):
            continue
        found.append(player)
    return tuple(found)


@value("Is In Line of Sight")
def _line_of_sight(ctx, start, end, barriers="Barriers Do Not Block LOS"):
    return bool(ctx.world.line_of_sight(vector_of(ctx, start), vector_of(ctx, end), barriers))


@value("Entity Exists")
def _exists(ctx, item):
    entity = entity_of(item)
    return entity is not None and bool(ctx.world.exists(entity))


@value("Velocity Of")
def _velocity(ctx, player):
    entity = entity_of(player)
    return (ctx.world.velocity(entity) if entity is not None else None) or ZERO


@value("Speed Of")
def _speed(ctx, player):
    return length(_velocity(ctx, player))


@value("Horizontal Speed Of")
def _horizontal_speed(ctx, player):
    v = _velocity(ctx, player)
    return math.hypot(v.x, v.z)


@value("Vertical Speed Of")
def _vertical_speed(ctx, player):
    return _velocity(ctx, player).y


@value("Speed Of In Direction")
def _speed_in_direction(ctx, player, direction):
    return _dot(ctx, _velocity(ctx, player), normalize(vector_of(ctx, direction)))


@value("Eye Position")
def _eye(ctx, player):
    entity = entity_of(player)
    return (ctx.world.eye_position(entity) if entity is not None else None) or _position(ctx, player)


# --- Workshop Settings and server load ---------------------------------------------------------


def _setting(ctx, category, name, default):
    return ctx.engine.settings.get((to_text(ctx, category), to_text(ctx, name)), default)


@value("Workshop Setting Toggle")
def _setting_toggle(ctx, category, name, default=False, sort=0):
    return truthy(_setting(ctx, category, name, default))


@value("Workshop Setting Integer", "Workshop Setting Real")
def _setting_number(ctx, category, name, default=0, low=None, high=None, sort=0):
    result = to_number(_setting(ctx, category, name, default))
    if low is not None:
        result = max(result, to_number(low))
    if high is not None:
        result = min(result, to_number(high))
    return result


@value("Workshop Setting Hero")
def _setting_hero(ctx, category, name, default=None, sort=0):
    found = _setting(ctx, category, name, default)
    return Hero(found) if isinstance(found, str) else found


@value("Workshop Setting Combo")
def _setting_combo(ctx, category, name, default=0, options=(), sort=0):
    found = int(to_number(_setting(ctx, category, name, default)))
    return float(found if 0 <= found < max(len(as_array(options)), 1) else to_number(default))


def _load(ctx, steps: list[int]) -> float:
    """Our own measure: the share of the per-frame action budget the script used, as a percentage."""
    return 100.0 * max(steps, default=0) / MAX_STEPS


@value("Server Load")
def _server_load(ctx):
    return _load(ctx, ctx.engine.frame_steps[-1:])


@value("Server Load Average")
def _server_load_average(ctx):
    steps = ctx.engine.frame_steps
    return 100.0 * (sum(steps) / len(steps)) / MAX_STEPS if steps else 0.0


@value("Server Load Peak")
def _server_load_peak(ctx):
    return _load(ctx, ctx.engine.frame_steps)


# --- helpers the engine uses ---------------------------------------------------------------------


def modify(ctx, current, operation: str, operand):
    """Modify Variable and the unnamed operation value."""
    if operation not in MODIFY_OPERATIONS:
        raise WorkshopError(f"unknown modify operation {operation!r}")
    if operation == "Append To Array":
        return _append(ctx, current, operand)
    if operation == "Remove From Array By Value":
        return _remove(ctx, as_array(current), operand)
    if operation == "Remove From Array By Index":
        items, index = as_array(current), to_index(operand)
        return items[:index] + items[index + 1 :] if 0 <= index < len(items) else items
    return _arith(ctx, operation, current, operand)


def interpolate(ctx, start, end, share: float):
    if isinstance(start, Vec3) or isinstance(end, Vec3):
        a, b = vector_of(ctx, start), vector_of(ctx, end)
        return Vec3(*(x + (y - x) * share for x, y in zip(a, b, strict=True)))
    a, b = to_number(start), to_number(end)
    return a + (b - a) * share


def approach(ctx, current, target, step: float):
    """`current` moved towards `target` by at most `step`."""
    step = abs(step)
    if isinstance(current, Vec3) or isinstance(target, Vec3):
        a, b = vector_of(ctx, current), vector_of(ctx, target)
        delta = _vec(lambda x, y: y - x, a, b)
        size = length(delta)
        if size <= step or size == 0:
            return b
        return Vec3(*(x + d * step / size for x, d in zip(a, delta, strict=True)))
    a, b = to_number(current), to_number(target)
    if abs(b - a) <= step:
        return b
    return a + math.copysign(step, b - a)


def implemented() -> frozenset:
    """The value names this module computes without asking the World."""
    return frozenset(VALUES)


__all__ = [
    "ALL_TEAMS",
    "TEAM_1",
    "TEAM_2",
    "Button",
    "Color",
    "Context",
    "GameMap",
    "GameMode",
    "Hero",
    "Team",
    "Unsupported",
    "as_array",
    "compare",
    "entity_of",
    "evaluate",
    "implemented",
    "modify",
    "players_of",
    "team",
    "text",
    "to_number",
    "to_text",
    "truthy",
    "value",
    "values_equal",
    "vector_of",
]
