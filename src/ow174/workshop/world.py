"""What the Workshop engine asks of the game, and an in-memory game for tests.

World is the interface: the engine calls it for players and their basic state, for every value it does
not compute itself (World.query) and for every action that is not flow control or a variable
(World.action). Each method has a default for a world without that part, and an unanswerable question
raises engine.Unsupported, so a script stops at the first thing the world cannot do instead of running
with an invented answer.

SimpleWorld keeps players and a few game facts in memory and performs a small set of actions on them
(move, face, damage, heal, kill, respawn, scores, messages). Every action it performs or does not know is
recorded in `actions`, in order, with its evaluated parameters.
"""

import random
from dataclasses import dataclass, field
from typing import ClassVar

from ow174.game.script.expr import Entity, Vec3
from ow174.workshop.engine import ActionCall, Unsupported
from ow174.workshop.values import (
    ALL_TEAMS,
    Hero,
    Team,
    entity_of,
    players_of,
    to_number,
    to_text,
    vector_of,
)


class World:
    def __init__(self, seed: int = 1) -> None:
        self.rng = random.Random(seed)
        self.engine = None

    def attach(self, engine) -> None:
        self.engine = engine

    def begin_frame(self, engine) -> None:
        """Called before the engine runs a frame."""

    def end_frame(self, engine) -> None:
        """Called after the engine ran a frame."""

    def players(self) -> list[Entity]:
        return []

    def team_of(self, player: Entity) -> str:
        raise Unsupported("player question", "team")

    def slot_of(self, player: Entity) -> int:
        raise Unsupported("player question", "slot")

    def hero_of(self, player: Entity):
        raise Unsupported("player question", "hero")

    def is_alive(self, player: Entity) -> bool:
        raise Unsupported("player question", "alive")

    def position(self, entity: Entity) -> Vec3 | None:
        raise Unsupported("player question", "position")

    def eye_position(self, entity: Entity | None) -> Vec3 | None:
        return None

    def facing(self, entity: Entity) -> Vec3 | None:
        raise Unsupported("player question", "facing")

    def velocity(self, entity: Entity) -> Vec3 | None:
        raise Unsupported("player question", "velocity")

    def exists(self, entity: Entity) -> bool:
        return entity in self.players()

    def name_of(self, entity: Entity) -> str:
        return f"Player {entity.id:08X}"

    def line_of_sight(self, start: Vec3, end: Vec3, barriers) -> bool:
        raise Unsupported("world question", "line of sight")

    def query(self, name: str, args: tuple, ctx):
        raise Unsupported("value", name)

    def action(self, call: ActionCall):
        raise Unsupported("action", call.name)

    def log(self, text: str) -> None:
        """Log To Inspector."""


ORIGIN = Vec3(0.0, 0.0, 0.0)
FORWARD = Vec3(0.0, 0.0, 1.0)


@dataclass
class PlayerState:
    entity: Entity
    team: str = "Team 1"
    slot: int = 0
    hero: str | None = None
    position: Vec3 = ORIGIN
    facing: Vec3 = FORWARD
    velocity: Vec3 = ORIGIN
    health: float = 200.0
    max_health: float = 200.0
    alive: bool = True
    name: str = ""
    score: float = 0.0
    held: set = field(default_factory=set)  # held button names
    facts: dict = field(default_factory=dict)  # any other value by name: "Is Crouching", "Ammo", ...


class SimpleWorld(World):
    """An in-memory game: players, team scores, match facts and a record of every action."""

    PLAYER_VALUES: ClassVar[dict] = {
        "Health": lambda state: state.health,
        "Max Health": lambda state: state.max_health,
        "Normalized Health": lambda state: state.health / state.max_health if state.max_health else 0.0,
        "Score Of": lambda state: state.score,
        "Has Spawned": lambda state: True,
        "Is On Ground": lambda state: state.position.y <= 0.0,
        "Is In Air": lambda state: state.position.y > 0.0,
        "Altitude Of": lambda state: max(state.position.y, 0.0),
        "Eye Position": lambda state: Vec3(state.position.x, state.position.y + 1.6, state.position.z),
        "Throttle Of": lambda state: Vec3(0.0, 0.0, 0.0),
        "Is Dummy Bot": lambda state: False,
    }

    def __init__(self, seed: int = 1) -> None:
        super().__init__(seed)
        self.states: dict[int, PlayerState] = {}
        self.facts: dict[str, object] = {}  # game values by name: "Match Time", "Is Game In Progress", ...
        self.team_scores = {"Team 1": 0.0, "Team 2": 0.0}
        self.actions: list[tuple[str, tuple]] = []
        self.messages: list[tuple[str, tuple, str]] = []  # (kind, recipients, text)
        self.logged: list[str] = []

    # --- players -------------------------------------------------------------------------------

    def add_player(self, entity_id: int, **fields) -> Entity:
        entity = Entity(entity_id)
        self.states[entity_id] = PlayerState(entity, **fields)
        return entity

    def remove_player(self, entity: Entity) -> None:
        self.states.pop(entity.id, None)

    def state(self, entity: Entity) -> PlayerState:
        found = self.states.get(entity.id)
        if found is None:
            raise Unsupported("player", f"{entity.id:08X}")
        return found

    def players(self) -> list[Entity]:
        return [state.entity for state in sorted(self.states.values(), key=lambda s: (s.team, s.slot))]

    def team_of(self, player):
        return self.state(player).team

    def slot_of(self, player):
        return self.state(player).slot

    def hero_of(self, player):
        hero = self.state(player).hero
        return Hero(hero) if hero is not None else None

    def is_alive(self, player):
        return self.state(player).alive

    def position(self, entity):
        state = self.states.get(entity.id) if entity is not None else None
        return state.position if state is not None else None

    def eye_position(self, entity):
        state = self.states.get(entity.id) if entity is not None else None
        return self.PLAYER_VALUES["Eye Position"](state) if state is not None else None

    def facing(self, entity):
        state = self.states.get(entity.id) if entity is not None else None
        return state.facing if state is not None else None

    def velocity(self, entity):
        state = self.states.get(entity.id) if entity is not None else None
        return state.velocity if state is not None else None

    def exists(self, entity):
        return entity.id in self.states

    def name_of(self, entity):
        state = self.states.get(entity.id)
        return (state.name or state.hero or f"Player {state.slot}") if state is not None else "null"

    def line_of_sight(self, start, end, barriers):
        return True  # an empty map

    # --- values --------------------------------------------------------------------------------

    def query(self, name, args, ctx):
        player = entity_of(args[0]) if args else None
        if player is not None and player.id in self.states:
            state = self.states[player.id]
            if name in self.PLAYER_VALUES:
                return self.PLAYER_VALUES[name](state)
            if name == "Is Button Held":
                return getattr(args[1], "name", args[1]) in state.held
            if name in state.facts:
                return state.facts[name]
        if name == "Team Score":
            team = args[0] if args else ALL_TEAMS
            return self.team_scores.get(getattr(team, "name", team), 0.0)
        if name in self.facts:
            return self.facts[name]
        return super().query(name, args, ctx)

    # --- actions -------------------------------------------------------------------------------

    def action(self, call):
        values = call.values()
        self.actions.append((call.name, values))
        handler = getattr(self, "_" + call.name.lower().replace(" ", "_").replace("-", "_"), None)
        if handler is None:
            raise Unsupported("action", call.name)
        handler(call, values)
        return None

    def log(self, text):
        self.logged.append(text)

    def _each(self, players):
        return [self.states[player.id] for player in players_of(players) if player.id in self.states]

    def _big_message(self, call, values):
        self.messages.append(("big", tuple(players_of(values[0])), to_text(call.ctx, values[1])))

    def _small_message(self, call, values):
        self.messages.append(("small", tuple(players_of(values[0])), to_text(call.ctx, values[1])))

    def _teleport(self, call, values):
        for state in self._each(values[0]):
            state.position = vector_of(call.ctx, values[1])

    def _set_facing(self, call, values):
        for state in self._each(values[0]):
            state.facing = vector_of(call.ctx, values[1])

    def _damage(self, call, values):
        for state in self._each(values[0]):
            if state.alive:
                state.health = max(0.0, state.health - max(0.0, to_number(values[2])))
                if state.health == 0.0:
                    self._die(call, state, entity_of(values[1]))

    def _heal(self, call, values):
        for state in self._each(values[0]):
            if state.alive:
                state.health = min(state.max_health, state.health + max(0.0, to_number(values[2])))

    def _kill(self, call, values):
        for state in self._each(values[0]):
            if state.alive:
                state.health = 0.0
                self._die(call, state, entity_of(values[1]))

    def _die(self, call, state, attacker):
        state.alive = False
        engine = call.ctx.engine
        engine.fire("Player Died", state.entity, Attacker=attacker, Victim=state.entity)
        if attacker is not None and attacker.id in self.states:
            engine.fire("Player Earned Elimination", attacker, Attacker=attacker, Victim=state.entity)

    def _resurrect(self, call, values):
        for state in self._each(values[0]):
            state.alive, state.health = True, state.max_health

    _respawn = _resurrect

    def _set_max_health(self, call, values):
        for state in self._each(values[0]):
            state.max_health = state.max_health * max(0.0, to_number(values[1])) / 100.0
            state.health = min(state.health, state.max_health)

    def _modify_player_score(self, call, values):
        for state in self._each(values[0]):
            state.score += to_number(values[1])

    def _set_player_score(self, call, values):
        for state in self._each(values[0]):
            state.score = to_number(values[1])

    def _modify_team_score(self, call, values):
        team = getattr(values[0], "name", values[0])
        for name in ("Team 1", "Team 2") if team == "All Teams" else (team,):
            self.team_scores[name] = self.team_scores.get(name, 0.0) + to_number(values[1])

    def _set_team_score(self, call, values):
        team = getattr(values[0], "name", values[0])
        for name in ("Team 1", "Team 2") if team == "All Teams" else (team,):
            self.team_scores[name] = to_number(values[1])

    def _declare_team_victory(self, call, values):
        self.facts["Is Match Complete"] = True
        self.facts["Winner"] = getattr(values[0], "name", values[0]) if values else None

    def _declare_match_draw(self, call, values):
        self.facts["Is Match Complete"] = True
        self.facts["Winner"] = None


__all__ = ["PlayerState", "SimpleWorld", "Team", "World"]
