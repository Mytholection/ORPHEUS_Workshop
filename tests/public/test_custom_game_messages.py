"""Custom game and Workshop script messages: the schema, presence, wire form and helpers."""

import unittest

from ow174.workshop import messages
from ow174.workshop.messages import (
    CGOptions,
    CustomGameError,
    PBCGLogic,
    PBCGLogicAction,
    PBCGLogicParam,
    decode,
    enabled,
    encode,
    to_plain,
)


def sample_logic() -> PBCGLogic:
    logic = PBCGLogic()
    rule = logic.entries.add(comment="first rule")
    rule.target.type = 1
    rule.target.team = 2
    condition = rule.conditions.add(invert=True, index=4)
    condition.params.add(valueIdentifier=17)
    condition.params.add(enumVal=3)
    action = rule.actions.add(index=9, comment="greet")
    action.params.add(valueIdentifier=40, valueParams=[1, 2], valueStr="Hello", valueStrs=["a", "b"])
    rule.actions.add(index=2, disabled=True)
    logic.entries.add(disabled=True)
    entity = logic.entities.add(type=1)
    entity.pos.x, entity.pos.y, entity.pos.z = 1.0, 2.5, -3.0
    logic.globalVariables.add(name="score")
    logic.playerVariables.add(name="lives")
    logic.subroutines.add(name="reset")
    setting = logic.userSettingInsts.add(name="Speed", type=2, heroGUIDs=[0x02E000000000012F])
    setting.val.x = 150.0
    logic.extensions.extend([3, 5])
    return logic


class SchemaTests(unittest.TestCase):
    def test_schema_has_the_client_file_shape(self):
        self.assertEqual(len(messages.MESSAGES), 22)
        self.assertEqual(len(messages.ENUMS), 5)
        self.assertEqual(sum(len(fields) for fields in messages.MESSAGES.values()), 110)
        file = messages.file_descriptor()
        self.assertEqual(file.name, "game/Core/Utilities/Protobuf/CustomGame.proto")
        self.assertEqual(file.package, "")
        self.assertEqual([message.name for message in file.message_type], list(messages.MESSAGES))

    def test_every_field_names_a_scalar_or_a_declared_type(self):
        for name, fields in messages.MESSAGES.items():
            numbers = [number for number, _, _, _ in fields]
            self.assertEqual(numbers, sorted(set(numbers)), name)
            for _, field, kind, label in fields:
                self.assertIn(label, (messages.OPTIONAL, messages.REPEATED), f"{name}.{field}")
                self.assertTrue(
                    kind in messages.SCALARS or kind in messages.MESSAGES or kind in messages.ENUMS,
                    f"{name}.{field}: {kind}",
                )
        self.assertNotIn(12, [number for number, _, _, _ in messages.MESSAGES["CGOptions"]])

    def test_unknown_message_names_are_reported(self):
        with self.assertRaises(CustomGameError):
            decode("CGNoSuchMessage", b"")


class WireTests(unittest.TestCase):
    def test_action_matches_hand_written_wire_bytes(self):
        # index = 5 (field 1 varint), disabled = true (field 3 varint), comment = "hi" (field 4).
        data = bytes([0x08, 0x05, 0x18, 0x01, 0x22, 0x02]) + b"hi"
        action = decode("PBCGLogicAction", data)
        self.assertEqual((action.index, action.disabled, action.comment), (5, True, "hi"))
        self.assertEqual(len(action.params), 0)
        self.assertEqual(encode(action), data)

    def test_repeated_scalars_are_not_packed(self):
        param = PBCGLogicParam(unusedValueParams=[7], valueParams=[1, 300])
        # Field 6 varint 7, then field 7 once per value: 1 and 300 (0xAC 0x02).
        self.assertEqual(encode(param), bytes([0x30, 0x07, 0x38, 0x01, 0x38, 0xAC, 0x02]))
        team = messages.CLASSES["CGGameRulesetTeam"](heroGUIDs=[2, 3])
        self.assertEqual(encode(team), bytes([0x20, 0x02, 0x20, 0x03]))
        self.assertEqual(encode(PBCGLogic(extensions=[4, 4])), bytes([0x40, 0x04, 0x40, 0x04]))

    def test_presence_survives_zero_and_false_values(self):
        pair = messages.CLASSES["CGGameRulesetVarValuePair"](
            varGUID=0, intValue=0, boolValue=False, floatValue=0.0
        )
        data = encode(pair)
        self.assertEqual(data, bytes([0x08, 0x00, 0x10, 0x00, 0x20, 0x00, 0x2D, 0, 0, 0, 0]))
        again = decode("CGGameRulesetVarValuePair", data)
        self.assertTrue(again.HasField("varGUID") and again.HasField("boolValue"))
        self.assertFalse(again.HasField("enumGUIDValue"))
        expected = {"varGUID": 0, "intValue": 0, "boolValue": False, "floatValue": 0.0}
        self.assertEqual(to_plain(again), expected)
        self.assertEqual(encode(messages.CLASSES["CGGameRulesetVarValuePair"]()), b"")

    def test_whole_custom_game_round_trips(self):
        options = CGOptions(description="test mode", minimumLatencyNS=-1, datacenterOverrideStr="local")
        options.mapRules.nextMapRule = 2
        options.mapRules.mapChangeRule = 3
        options.teamRules.performTeamShuffleRule = 3
        options.teamRules.maxObservers = 2
        options.rulesetMapPairs.add(mapGUID=0x0688, savedGameIndex=0, isRulesetCleared=False)
        ruleset = options.savedGameRulesets.add(gameModeGUID=0x20, flags=1, logicStr='rule("first rule") {}')
        ruleset.masterVars.add(varGUID=1, floatValue=1.5)
        team = ruleset.teams.add(teamIndex=1, numTeamMembers=6, heroesArrayIsWhitelist=True)
        team.heroGUIDs.append(0x02E000000000012F)
        team.bodyVars.add(heroGUID=0x02E000000000012F).bodyVars.add(varGUID=9, intValue=200)
        ruleset.logic.CopyFrom(sample_logic())
        options.rootLogic.CopyFrom(sample_logic())
        options.linkIdentity.gameTitle = "Test"
        options.linkIdentity.creatorID.src = 1
        persisted = messages.PersistedCGSettings(version=3)
        persisted.options.CopyFrom(options)

        data = encode(persisted)
        again = decode("PersistedCGSettings", data)
        self.assertEqual(again, persisted)
        self.assertEqual(encode(again), data)
        random_next_map = messages.ENUMS["CGNextMapRule"]["RandomNextMapRule"]
        self.assertEqual(again.options.mapRules.nextMapRule, random_next_map)
        self.assertEqual(again.options.minimumLatencyNS, -1)

        logic = again.options.savedGameRulesets[0].logic
        rules = enabled(logic.entries)
        self.assertEqual(len(rules), 1)
        self.assertEqual(len(enabled(rules[0].conditions)), 1)
        self.assertEqual([action.index for action in enabled(rules[0].actions)], [9])
        plain = to_plain(logic)
        self.assertEqual(plain["entries"][0]["target"], {"type": 1, "team": 2})
        self.assertEqual(plain["entries"][0]["actions"][0]["params"][0]["valueParams"], [1, 2])
        self.assertEqual(plain["entities"][0]["pos"], {"x": 1.0, "y": 2.5, "z": -3.0})
        self.assertEqual(plain["entries"][1], {"disabled": True})

    def test_unknown_fields_are_skipped_and_damage_is_reported(self):
        # Field 12 does not exist in CGOptions; description (field 7) follows it.
        options = decode("CGOptions", bytes([0x60, 0x01, 0x3A, 0x01]) + b"x")
        self.assertEqual(options.description, "x")
        self.assertEqual(to_plain(options), {"description": "x"})
        # A string of length 5 with one byte of content.
        with self.assertRaises(CustomGameError):
            decode("CGOptions", bytes([0x3A, 0x05]) + b"x")

    def test_enabled_keeps_order_and_drops_disabled_items(self):
        actions = [PBCGLogicAction(index=index, disabled=index == 2) for index in (1, 2, 3)]
        self.assertEqual([action.index for action in enabled(actions)], [1, 3])


if __name__ == "__main__":
    unittest.main()
