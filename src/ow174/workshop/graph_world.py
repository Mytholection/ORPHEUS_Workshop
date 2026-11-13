"""A Workshop world that performs actions by running the client's own action graphs.

GraphWorld connects the rule engine to upstream's statescript runtime inside a scene.SceneWorld. The game
entity (runtime.GAME_MODE_ENTITY) and every player are bound scene entities with their own script
component and PlayScript queue, so the game messages an action graph sends and the helper scripts it
plays reach their targets through the scene's own routing, as they do in upstream's server.

An action the catalog gives a graph runs as one instance of that graph on the game entity's component.
Its parameter list (variable 18739) holds:
- for a value parameter, a Parameter: the action graph's parameter config var asks the engine for its
  current value every time it is read, so a state that watches a parameter sees it change;
- for a dropdown, the chosen option's identifier;
- for a constant, the constant.
The action is finished when its graph reaches the Workshop "done" node. Its instance stays alive after
that when the graph keeps states running (a created effect, a disabled HUD), until a later action ends it.

Engine values become statescript values: numbers float32, vectors, players (entities), booleans, text,
null and arrays of these. Heroes, teams, buttons, maps, game modes and colours are not converted yet:
an action that passes one stops with engine.Unsupported.

Players, their state and every value about the game come from a second world (`players`, for example a
SimpleWorld), because a scene of action graphs alone has no players or match. The bundle and catalog are
local game data from tools/extract_workshop_graphs.py and DataTool's `list-workshop`.
"""

import gzip
import json
from dataclasses import dataclass
from pathlib import Path

from ow174.game.script import expr, play_queue, runtime, scene
from ow174.game.script.expr import INSTANCE, Entity, Vec3
from ow174.game.script.graph import Graph
from ow174.workshop import actions
from ow174.workshop.engine import ActionCall, Unsupported
from ow174.workshop.values import Button, Color, GameMap, GameMode, Hero, Team
from ow174.workshop.world import World

GAME = runtime.GAME_MODE_ENTITY


def full_guid(text: str) -> int:
    """'000000004A29.01C' -> the 64-bit key with the type bits, as DataTool's XML names it."""
    index, kind = text.split(".")
    return int(f"{int(kind, 16) - 1:012b}"[::-1], 2) << 48 | int(index, 16)


def to_script(value):
    """An engine value as a statescript value."""
    if value is None or isinstance(value, (bool, str, Entity)):
        return value
    if isinstance(value, (int, float)):
        return expr.f32(float(value))
    if isinstance(value, Vec3):
        return Vec3(*(expr.f32(float(axis)) for axis in value))
    if isinstance(value, tuple):
        return tuple(to_script(item) for item in value)
    if isinstance(value, (Hero, Team, Button, GameMap, GameMode, Color)):
        raise Unsupported("graph parameter type", type(value).__name__)
    raise Unsupported("graph parameter type", type(value).__name__)


@dataclass
class Parameter:
    """A value parameter of a running action: evaluated again whenever the graph reads it."""

    call: ActionCall
    index: int

    def current(self):
        return to_script(self.call.value(self.index))


@dataclass
class ActionRun:
    """One action performed by its graph. The engine holds the rule until `done`."""

    name: str
    instance: runtime.Instance
    done: bool = False


class ActionScene(actions.ActionHost, scene.SceneWorld):
    """The scene the action graphs run in."""

    def __init__(self, graphs: dict[int, Graph]) -> None:
        super().__init__()
        self.graphs = graphs
        self.runs: dict[tuple[int, int], ActionRun] = {}
        self.flows: list[tuple[int, actions.Flow]] = []

    def workshop_parameter(self, instance, parameter, entity):
        return parameter.current() if isinstance(parameter, Parameter) else parameter

    def workshop_done(self, instance):
        root = instance
        while root.parent is not None:
            root = root.parent
        run = self.runs.get((root.component.entity, root.id))
        if run is not None:
            run.done = True

    def workshop_flow(self, instance, flow):
        self.flows.append((instance.graph.index, flow))  # the engine performs flow control itself

    # Entity-to-entity config vars of the action graphs (OWLib bases them on STUConfigVarEntityID). The
    # graphs apply them to a player to get the entity a per-player branch acts on. In this scene a player
    # is one entity, so each names the entity itself; in upstream's server a player has a controller and
    # a body, and which one each names is not established.
    RELATED_ENTITY = ("STU_69DBE90D", "STU_0165541D")

    def native(self, cfg, instance):
        cls = cfg.get("$")
        if cls == "STU_A3DEF368":  # the game entity, as the global variable graphs use it
            return Entity(GAME)
        if cls in self.RELATED_ENTITY and instance is not None:
            target = cfg.get("m_entity")
            entity = (
                expr.to_entity(instance.evaluate(target)) if target is not None else instance.component.entity
            )
            return Entity(entity) if expr.valid_entity(entity) else None
        if cls == "STU_8985E00A" and instance is not None:  # no fields: the instance's own entity
            return Entity(instance.component.entity)
        return super().native(cfg, instance)

    def acquire(self, guid: int):
        found = self.graphs.get(guid & 0xFFFFFFFFFFFF) if guid >> 48 == 0x0580 else None
        return play_queue.Load("ready", found) if found is not None else None


class GraphWorld(World):
    def __init__(self, bundle: dict, catalog: dict, players: World, *, strict: bool = True) -> None:
        super().__init__()
        self.players_world = players
        self.rng = players.rng
        self.strict = strict
        graphs = {record["index"]: Graph(record) for record in bundle["graphs"]}
        self.action_graphs = {
            item["name"]: item["graph"] for item in bundle["workshop"]["actions"] if item["graph"] is not None
        }
        self.parameters = {item["DisplayName"]: item.get("Parameters") or [] for item in catalog["Actions"]}
        self.options = {
            dropdown["Id"]: {option["DisplayName"]: option["VirtualId"] for option in dropdown["Options"]}
            for dropdown in catalog.get("Dropdowns") or []
        }
        self.scene = ActionScene(graphs)
        self.components: dict[int, runtime.Component] = {}
        self._bind(GAME)

    @classmethod
    def from_files(cls, bundle: Path, catalog: Path, players: World, **options) -> "GraphWorld":
        data = json.loads(gzip.decompress(Path(bundle).read_bytes()))
        return cls(data, json.loads(Path(catalog).read_text(encoding="utf-8-sig")), players, **options)

    def _bind(self, entity: int) -> runtime.Component:
        self.scene.bind(entity)
        component = runtime.Component(entity, world=self.scene, strict=self.strict)
        self.scene.bind_script_component(entity, component)
        self.scene.set_play_queue(entity, play_queue.Queue(component, self.scene.acquire))
        self.components[entity] = component
        return component

    # --- frames --------------------------------------------------------------------------------

    def attach(self, engine) -> None:
        super().attach(engine)
        self.players_world.attach(engine)

    def begin_frame(self, engine) -> None:
        self.players_world.begin_frame(engine)
        for player in self.players_world.players():
            if player.id not in self.components:
                self._bind(player.id)
        for component in list(self.components.values()):
            component.run_frame(engine.frame)
        for key, run in list(self.scene.runs.items()):
            if run.done and run.instance.stopped:
                del self.scene.runs[key]

    def end_frame(self, engine) -> None:
        self.players_world.end_frame(engine)

    # --- actions -------------------------------------------------------------------------------

    def action(self, call: ActionCall):
        index = self.action_graphs.get(call.name)
        if index is None:
            return self.players_world.action(call)
        definition = self.scene.graphs[index]
        params = tuple(
            self._parameter(call, position, spec)
            for position, spec in enumerate(self.parameters.get(call.name, ()))
        )
        component = self.components[GAME]
        instance = component.create(definition, values={(INSTANCE, actions.PARAMETERS): params})
        run = ActionRun(call.name, instance)
        self.scene.runs[(GAME, instance.id)] = run
        component.run_now()
        return run

    def _parameter(self, call: ActionCall, position: int, spec: dict):
        kind = spec.get("InferredType")
        raw = call.args[position] if position < len(call.args) else None
        if kind == "Dropdown":
            options = self.options.get(spec.get("DropdownId"), {})
            name = raw if isinstance(raw, str) else None
            if name not in options:
                raise Unsupported("dropdown option", f"{call.name}: {raw!r}")
            return expr.Asset(full_guid(options[name]))
        if kind == "GenericInput":
            return Parameter(call, position)
        return to_script(call.value(position))

    # --- everything else comes from the players' world -----------------------------------------

    def players(self):
        return self.players_world.players()

    def team_of(self, player):
        return self.players_world.team_of(player)

    def slot_of(self, player):
        return self.players_world.slot_of(player)

    def hero_of(self, player):
        return self.players_world.hero_of(player)

    def is_alive(self, player):
        return self.players_world.is_alive(player)

    def position(self, entity):
        return self.players_world.position(entity)

    def eye_position(self, entity):
        return self.players_world.eye_position(entity)

    def facing(self, entity):
        return self.players_world.facing(entity)

    def velocity(self, entity):
        return self.players_world.velocity(entity)

    def exists(self, entity):
        return self.players_world.exists(entity)

    def name_of(self, entity):
        return self.players_world.name_of(entity)

    def line_of_sight(self, start, end, barriers):
        return self.players_world.line_of_sight(start, end, barriers)

    def query(self, name, args, ctx):
        return self.players_world.query(name, args, ctx)

    def log(self, text):
        self.players_world.log(text)


__all__ = ["GAME", "ActionRun", "ActionScene", "GraphWorld", "Parameter", "full_guid", "to_script"]
