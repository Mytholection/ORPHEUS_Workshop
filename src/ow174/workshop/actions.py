"""The client's Workshop action graphs, run by the statescript runtime.

In build 104319 a Workshop action is a small statescript graph in the game data: the Workshop catalog
names a 01B graph for 211 of its 222 actions. A graph reads the action's parameters, drives the game's
ordinary scripts (it sets a variable, sends a game message or plays a script) and ends in a node that
reports the action finished. The remaining actions (If, While, For, Call Subroutine, ...) have no graph;
they belong to the rule engine.

This module supplies the pieces of those graphs that only the Workshop uses, so the runtime in
ow174.game.script can run them unchanged:

- PARAMETER (STU_77B0987E), a config var. Its m_35547D6E reads one element of instance variable
  PARAMETERS, the action's parameter list; m_entity optionally names the entity the parameter is read
  for; m_FDCA1FD0 and m_68CFF844 are the lower and upper limit.
- DONE (STU_1E93FE1F), the last node of every action graph.
- ABORT (STU_ADAFD7FF) and LOOP (STU_99ED4486), each with two flags, and SKIP (STU_DC325C52) with a
  count: the graphs of Abort, Loop, Skip and their variants consist of one of these and DONE.
- SET_ENTITY_VARIABLE (STU_0BDBC7B2): SetVar's fields plus m_entity. Its out var is a plain variable or
  an expression ending in the Workshop variable opcode (expr.WORKSHOP_VARIABLE).

What is established and what is not:
- Read in the client: the Workshop variable opcode (interpreter 1B81210, case 0x48; see expr.py).
- Read in the game data: the classes above, their fields and how the 211 graphs use them. The meaning
  of the two flags comes from the three authored variants: Abort has neither, Abort If Condition Is True
  has the first and Abort If Condition Is False the second, and Loop repeats the pattern.
- Our own design: the ActionHost interface below. The native handlers of these classes were not read,
  so what the original server did with a finished action or a flow request is not known. The limits are
  applied to numbers only; how the original treated a vector with limits is not known either.

A rule engine implements ActionHost on the component's World, starts one graph instance per action with
PARAMETERS set, and continues its rule when workshop_done arrives, in the same frame or a later one.
"""

from dataclasses import dataclass
from types import NotImplementedType

from ow174.game.script import (
    expr,
    nodes,  # noqa: F401 -- the action graphs also use the standard node handlers
    play,
)
from ow174.game.script.expr import ENTITY, to_entity, to_int, valid_entity
from ow174.game.script.runtime import Instance, handler

PARAMETERS = 18739  # the instance variable holding the action's parameter list
PARAMETER = "STU_77B0987E"
DONE = "STU_1E93FE1F"
ABORT = "STU_ADAFD7FF"
LOOP = "STU_99ED4486"
SKIP = "STU_DC325C52"
SET_ENTITY_VARIABLE = "STU_0BDBC7B2"


@dataclass(frozen=True)
class Flow:
    """What an Abort, Loop or Skip node asks of the rule that runs the action."""

    kind: str  # "abort", "loop" or "skip"
    if_true: bool = False  # only while the rule's conditions hold (m_F3733689)
    if_false: bool = False  # only while they do not hold (m_79252765)
    count: int = 0  # skip: how many of the following actions (m_C337E584)


class ActionHost:
    """What a running action graph asks of the rule engine. Mix it into the component's World, before
    runtime.World in the bases, and override the three workshop_ methods."""

    def workshop_parameter(self, instance: Instance, parameter, entity: int | None):
        """The current value of one element of the action's parameter list. A state that watches a
        parameter asks again on every tick, so the answer may change while the action runs. `entity`
        is the entity the graph reads the parameter for, when it names one."""
        return parameter

    def workshop_done(self, instance: Instance) -> None:
        """The action's graph reached its last node."""

    def workshop_flow(self, instance: Instance, flow: Flow) -> None:
        """The action asks to abort or restart its rule, or to skip actions."""

    def native(self, cfg: dict, instance: Instance | None):
        if cfg.get("$") == PARAMETER and instance is not None:
            return parameter(self, instance, cfg)
        return super().native(cfg, instance)


def limit(value, low, high):
    """A number kept within the limits that are numbers; any other value unchanged."""
    if not _number(value):
        return value
    if _number(low) and value < low:
        value = _as(value, low)
    if _number(high) and value > high:
        value = _as(value, high)
    return value


def _number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _as(value, bound):
    """A limit in the value's own type: a float stays a float32, an int stays an int."""
    return expr.f32(float(bound)) if isinstance(value, float) else to_int(bound)


def parameter(host: ActionHost, instance: Instance, cfg: dict):
    """Evaluate a PARAMETER config var: the list element, the host's value for it, then the limits."""
    element = instance.evaluate(cfg.get("m_35547D6E"))
    target = cfg.get("m_entity")
    entity = to_entity(instance.evaluate(target)) if target is not None else None
    value = host.workshop_parameter(instance, element, entity)
    return limit(value, instance.evaluate(cfg.get("m_FDCA1FD0")), instance.evaluate(cfg.get("m_68CFF844")))


def _host(instance: Instance, node) -> ActionHost | None:
    """The World as an action host. Without one, strict execution stops; otherwise the caller declines
    and the runtime keeps its policy for a node it has no model for."""
    world = instance.component.world
    if isinstance(world, ActionHost):
        return world
    if instance.component.strict:
        instance.component.unsupported(instance, "workshop action host", node.cls, node)
    return None


@handler(DONE)
def done(instance: Instance, node, caller) -> bool | NotImplementedType:
    host = _host(instance, node)
    if host is None:
        return NotImplemented
    host.workshop_done(instance)
    instance.follow(node, "m_outPlug", None)
    return True


@handler(ABORT, LOOP)
def flow(instance: Instance, node, caller) -> bool | NotImplementedType:
    host = _host(instance, node)
    if host is None:
        return NotImplemented
    kind = "abort" if node.cls == ABORT else "loop"
    host.workshop_flow(
        instance, Flow(kind, bool(node.fields.get("m_F3733689")), bool(node.fields.get("m_79252765")))
    )
    instance.follow(node, "m_outPlug", None)
    return True


@handler(SKIP)
def skip(instance: Instance, node, caller) -> bool | NotImplementedType:
    host = _host(instance, node)
    if host is None:
        return NotImplemented
    count = to_int(instance.evaluate(node.fields.get("m_C337E584")))
    host.workshop_flow(instance, Flow("skip", count=max(count, 0)))
    instance.follow(node, "m_outPlug", None)
    return True


@handler(SET_ENTITY_VARIABLE)
def set_entity_variable(instance: Instance, node, caller) -> bool:
    """Assign a variable of the entity m_entity names, then follow m_outPlug.

    Modelled on SetVar (nodes.set_var): the value, with int 0 for a failed evaluation, is assigned only
    when both the value and the out var are present. The out var names an entity variable either by a
    Workshop variable expression or as a plain variable. No authored graph sets m_index or m_key on this
    class, so they are unsupported here instead of guessed.
    """
    config, target = node.fields.get("m_value"), node.fields.get("m_out_Var")
    component = instance.component
    if node.fields.get("m_index") is not None or node.fields.get("m_key") is not None:
        if component.strict:
            component.unsupported(instance, "indexed or keyed entity variable", node.cls, node)
    elif config is not None and target is not None:
        value = play.evaluate_value(instance, config, initial=0)
        entity = to_entity(instance.evaluate(node.fields.get("m_entity")))
        var = expr.workshop_lvalue(target, instance.context())
        if var is None:
            found = expr.lvalue(target)
            var = found[1] if found is not None else None
        if var is not None and valid_entity(entity):
            _assign(instance, entity, var, value)
    instance.follow(node, "m_outPlug", None)
    return True


def _assign(instance: Instance, entity: int, var: int, value) -> None:
    """A plain assignment to an entity variable: the instance's own entity, or another entity's slot
    when the World declares one."""
    component = instance.component
    if entity == component.entity:
        instance.write((ENTITY, var), value)
        return
    slot = component.world.entity_var_slot(entity, var, create=True)
    if slot is NotImplemented or slot is None:
        if component.strict:
            component.unsupported(instance, "entity variable service", f"{entity:08X}:{var}")
        return
    before = slot.value()
    slot.base = value
    for link in list(slot.links):
        if link.state.active:
            link.state.var_written(slot)
    component.changed(slot, before)


__all__ = [
    "ABORT", "DONE", "LOOP", "PARAMETER", "PARAMETERS", "SET_ENTITY_VARIABLE", "SKIP",
    "ActionHost", "Flow", "limit", "parameter",
]
