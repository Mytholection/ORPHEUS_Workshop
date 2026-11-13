"""Custom game settings and Workshop scripts as build 104319 stores and sends them.

The client describes these messages in its embedded `CustomGame.proto` (proto2, no package): 22
messages and 5 enums. The schema below repeats their names, field numbers and types, so the message
classes exist without the client's descriptor. Every field is optional or repeated and repeated
scalars are not packed, so a decoded message keeps field presence and encodes back to its bytes.

A Workshop script is a `PBCGLogic`. Its rules are `PBCGLogicEntry` messages: a `PBCGLogicTarget`
(the event and the team, slot and hero it is limited to) with `PBCGLogicCondition` and
`PBCGLogicAction` lists. A condition or action names a catalog `index` and carries `PBCGLogicParam`
operands. What an index or a value identifier means comes from the client's catalog, which this
module does not hold. A whole custom game is a `CGOptions`; `PersistedCGSettings` is its saved form.

`tools/extract_custom_game_descriptor.py` cuts the descriptor out of a local client, and
`tests/runtime/test_custom_game_descriptor.py` compares this schema with it.
"""

from google.protobuf import descriptor_pb2, descriptor_pool, message_factory
from google.protobuf.message import DecodeError, Message

FILE_NAME = "game/Core/Utilities/Protobuf/CustomGame.proto"

OPTIONAL, REPEATED = 1, 3
SCALARS = {"float": 2, "int64": 3, "uint64": 4, "int32": 5, "bool": 8, "string": 9, "uint32": 13}
MESSAGE, ENUM = 11, 14

ENUMS = {
    "CGPerformTeamShuffleRule": {
        "EveryMatchPerformRule": 1,
        "OnMapFinishPerformRule": 2,
        "NeverPerformRule": 3,
    },
    "CGTeamShuffleRule": {"RandomShuffleRule": 1},
    "CGNextMapRule": {"InOrderNextMapRule": 1, "RandomNextMapRule": 2, "CalculateNextMapRule": 3},
    "CGMapChangeRule": {"EveryMapChangeRule": 1, "OnMapFinishMapChangeRule": 2, "NeverMapChangeRule": 3},
    "CGBackToLobbyRule": {
        "EveryMatchBackToLobbyRule": 1,
        "OnMapFinishBackToLobbyRule": 2,
        "NeverBackToLobbyRule": 3,
    },
}

# Message -> (field number, name, type, label), in the client's declaration order.
MESSAGES = {
    "CGGameRulesetBodyVars": (
        (1, "bodyVars", "CGGameRulesetVarValuePair", REPEATED),
        (2, "heroGUID", "uint64", OPTIONAL),
    ),
    "CGGameRulesetVarValuePair": (
        (1, "varGUID", "uint64", OPTIONAL),
        (2, "intValue", "int32", OPTIONAL),
        (3, "enumGUIDValue", "uint64", OPTIONAL),
        (4, "boolValue", "bool", OPTIONAL),
        (5, "floatValue", "float", OPTIONAL),
    ),
    "CGGameRulesetTeam": (
        (1, "teamIndex", "uint32", OPTIONAL),
        (2, "numTeamMembers", "uint32", OPTIONAL),
        (3, "heroesArrayIsWhitelist", "bool", OPTIONAL),
        (4, "heroGUIDs", "uint64", REPEATED),
        (5, "bodyVars", "CGGameRulesetBodyVars", REPEATED),
        (6, "allHeroBodyVars", "CGGameRulesetVarValuePair", REPEATED),
        (7, "controllerVars", "CGGameRulesetVarValuePair", REPEATED),
    ),
    "CGTeamRules": (
        (1, "performTeamShuffleRule", "CGPerformTeamShuffleRule", OPTIONAL),
        (2, "teamShuffleRule", "CGTeamShuffleRule", OPTIONAL),
        (3, "swapTeamsIfNoShuffle", "bool", OPTIONAL),
        (4, "maxObservers", "int32", OPTIONAL),
        (5, "pauseOnDisconnect", "bool", OPTIONAL),
    ),
    "CGMapRules": (
        (1, "nextMapRule", "CGNextMapRule", OPTIONAL),
        (2, "mapChangeRule", "CGMapChangeRule", OPTIONAL),
        (3, "backToLobbyRule", "CGBackToLobbyRule", OPTIONAL),
    ),
    "PBCGLogicTarget": (
        (1, "type", "int32", OPTIONAL),
        (2, "team", "int32", OPTIONAL),
        (3, "slot", "int32", OPTIONAL),
        (4, "hero", "uint64", OPTIONAL),
    ),
    "PBCGLogicParam": (
        (1, "enumVal", "int32", OPTIONAL),
        (2, "val", "uint64", OPTIONAL),
        (3, "isVar", "bool", OPTIONAL),
        (4, "isGlobalVar", "bool", OPTIONAL),
        (5, "valueIdentifier", "int32", OPTIONAL),
        (6, "unusedValueParams", "int32", REPEATED),
        (7, "valueParams", "uint64", REPEATED),
        (8, "valueStr", "string", OPTIONAL),
        (9, "valueStrs", "string", REPEATED),
    ),
    "PBCGLogicCondition": (
        (1, "invert", "bool", OPTIONAL),
        (2, "index", "int32", OPTIONAL),
        (3, "params", "PBCGLogicParam", REPEATED),
        (4, "disabled", "bool", OPTIONAL),
        (5, "comment", "string", OPTIONAL),
    ),
    "PBCGLogicAction": (
        (1, "index", "int32", OPTIONAL),
        (2, "params", "PBCGLogicParam", REPEATED),
        (3, "disabled", "bool", OPTIONAL),
        (4, "comment", "string", OPTIONAL),
    ),
    "PBCGLogicEntry": (
        (1, "target", "PBCGLogicTarget", OPTIONAL),
        (2, "conditions", "PBCGLogicCondition", REPEATED),
        (3, "actions", "PBCGLogicAction", REPEATED),
        (4, "comment", "string", OPTIONAL),
        (5, "disabled", "bool", OPTIONAL),
    ),
    "PBCGVec3": (
        (1, "x", "float", OPTIONAL),
        (2, "y", "float", OPTIONAL),
        (3, "z", "float", OPTIONAL),
    ),
    "PBCGEntityEntry": (
        (1, "type", "int32", OPTIONAL),
        (2, "pos", "PBCGVec3", OPTIONAL),
        (3, "facing", "PBCGVec3", OPTIONAL),
        (4, "up", "PBCGVec3", OPTIONAL),
        (5, "scale", "PBCGVec3", OPTIONAL),
    ),
    "PBCGVariableEntry": ((1, "name", "string", OPTIONAL),),
    "PBCGSubroutineEntry": ((1, "name", "string", OPTIONAL),),
    "PBCGLogicUserSettingInst": (
        (1, "name", "string", OPTIONAL),
        (2, "type", "int32", OPTIONAL),
        (3, "val", "PBCGVec3", OPTIONAL),
        (4, "heroGUIDs", "uint64", REPEATED),
    ),
    "PBCGLogic": (
        (1, "dummy", "uint32", OPTIONAL),
        (2, "entries", "PBCGLogicEntry", REPEATED),
        (3, "entities", "PBCGEntityEntry", REPEATED),
        (4, "globalVariables", "PBCGVariableEntry", REPEATED),
        (5, "playerVariables", "PBCGVariableEntry", REPEATED),
        (6, "subroutines", "PBCGSubroutineEntry", REPEATED),
        (7, "userSettingInsts", "PBCGLogicUserSettingInst", REPEATED),
        (8, "extensions", "uint32", REPEATED),
    ),
    "CGGameRuleset": (
        (1, "gameModeGUID", "uint64", OPTIONAL),
        (2, "gameRulesetGUID", "uint64", OPTIONAL),
        (3, "masterVars", "CGGameRulesetVarValuePair", REPEATED),
        (4, "globalAdminVars", "CGGameRulesetVarValuePair", REPEATED),
        (5, "teams", "CGGameRulesetTeam", REPEATED),
        (6, "flags", "uint32", OPTIONAL),
        (7, "logic", "PBCGLogic", OPTIONAL),
        (8, "logicStr", "string", OPTIONAL),
    ),
    "CGGameRulesetMapPair": (
        (1, "mapGUID", "uint64", OPTIONAL),
        (2, "savedGameIndex", "int32", OPTIONAL),
        (3, "isRulesetCleared", "bool", OPTIONAL),
    ),
    "CGPlayerID": (
        (1, "src", "uint64", OPTIONAL),
        (2, "seq", "uint64", OPTIONAL),
    ),
    "CGLinkIdentity": (
        (1, "gameTitle", "string", OPTIONAL),
        (2, "code", "string", OPTIONAL),
        (3, "creatorID", "CGPlayerID", OPTIONAL),
        (4, "creatorSecondaryAccountID", "CGPlayerID", OPTIONAL),
        (5, "creatorPlatform", "int32", OPTIONAL),
        (6, "hash", "uint64", OPTIONAL),
        (7, "avatarPortrait", "uint64", OPTIONAL),
        (8, "portraitFrame", "uint64", OPTIONAL),
        (9, "timestampSecs", "uint64", OPTIONAL),
        (10, "level", "int32", OPTIONAL),
    ),
    # The schema has no field 12.
    "CGOptions": (
        (1, "mapRules", "CGMapRules", OPTIONAL),
        (2, "teamRules", "CGTeamRules", OPTIONAL),
        (3, "rulesetMapPairs", "CGGameRulesetMapPair", REPEATED),
        (4, "savedGameRulesets", "CGGameRuleset", REPEATED),
        (5, "matchVoiceChatEnabled", "bool", OPTIONAL),
        (6, "datacenterOverride", "uint32", OPTIONAL),  # deprecated in the schema
        (7, "description", "string", OPTIONAL),
        (8, "rootLogic", "PBCGLogic", OPTIONAL),
        (9, "difficultyGUID", "uint64", OPTIONAL),
        (10, "allowSkirmishers", "bool", OPTIONAL),
        (11, "useBalanceTestIfAvailable", "bool", OPTIONAL),
        (13, "minimumLatencyNS", "int64", OPTIONAL),
        (14, "linkIdentity", "CGLinkIdentity", OPTIONAL),
        (15, "datacenterOverrideStr", "string", OPTIONAL),
    ),
    "PersistedCGSettings": (
        (1, "version", "int32", OPTIONAL),
        (2, "options", "CGOptions", OPTIONAL),
    ),
}


class CustomGameError(ValueError):
    """Bytes that are not the named message, or a message name the schema does not have."""


def file_descriptor() -> descriptor_pb2.FileDescriptorProto:
    """The schema as a protobuf file descriptor, as the client's own descriptor declares it."""
    file = descriptor_pb2.FileDescriptorProto(name=FILE_NAME)
    for name, fields in MESSAGES.items():
        message = file.message_type.add(name=name)
        for number, field_name, kind, label in fields:
            field = message.field.add(name=field_name, number=number, label=label)
            if kind in SCALARS:
                field.type = SCALARS[kind]
            else:
                field.type = ENUM if kind in ENUMS else MESSAGE
                field.type_name = "." + kind
    for name, values in ENUMS.items():
        enum = file.enum_type.add(name=name)
        for value_name, number in values.items():
            enum.value.add(name=value_name, number=number)
    return file


def _build_classes() -> dict[str, type[Message]]:
    pool = descriptor_pool.DescriptorPool()
    pool.Add(file_descriptor())
    return {name: message_factory.GetMessageClass(pool.FindMessageTypeByName(name)) for name in MESSAGES}


CLASSES = _build_classes()

CGOptions = CLASSES["CGOptions"]
CGGameRuleset = CLASSES["CGGameRuleset"]
PersistedCGSettings = CLASSES["PersistedCGSettings"]
PBCGLogic = CLASSES["PBCGLogic"]
PBCGLogicEntry = CLASSES["PBCGLogicEntry"]
PBCGLogicTarget = CLASSES["PBCGLogicTarget"]
PBCGLogicCondition = CLASSES["PBCGLogicCondition"]
PBCGLogicAction = CLASSES["PBCGLogicAction"]
PBCGLogicParam = CLASSES["PBCGLogicParam"]


def message_class(name: str) -> type[Message]:
    try:
        return CLASSES[name]
    except KeyError:
        raise CustomGameError(f"no custom game message named {name!r}") from None


def decode(name: str, data: bytes) -> Message:
    """One message of the schema from its bytes. Fields the schema does not have are skipped."""
    message = message_class(name)()
    try:
        message.ParseFromString(bytes(data))
    except DecodeError as error:
        raise CustomGameError(f"{name} is damaged: {error}") from error
    return message


def encode(message: Message) -> bytes:
    """The message's bytes, fields in number order, as the client writes them."""
    return message.SerializeToString(deterministic=True)


def enabled(items):
    """The rules, conditions or actions of a list that are not disabled, in their order."""
    return [item for item in items if not item.disabled]


def to_plain(message: Message) -> dict:
    """The fields that are present, by their schema names: numbers, strings, lists and nested dicts.

    A field that is present with a zero or false value is kept; an absent field has no key.
    """
    plain = {}
    for field, value in message.ListFields():
        nested = field.message_type is not None
        if field.is_repeated:
            plain[field.name] = [to_plain(item) if nested else item for item in value]
        else:
            plain[field.name] = to_plain(value) if nested else value
    return plain
