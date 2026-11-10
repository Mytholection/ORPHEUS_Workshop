//! Custom game settings and Workshop scripts as build 104319 stores and sends them.
//!
//! The client describes these messages in its embedded `CustomGame.proto` (proto2, no package).
//! Each type below names the message it mirrors. Every field is optional or repeated, repeated
//! scalars are not packed, and enums start at 1, so presence is kept with `Option` and a decoded
//! message encodes back to the bytes it came from.
//!
//! A Workshop script is a [`Logic`]: its rules are [`LogicEntry`] values, each with a
//! [`LogicTarget`] (the event and its filters), [`LogicCondition`] and [`LogicAction`] lists.
//! Conditions and actions name a catalog index and carry [`LogicParam`] operands. What an index
//! or a value identifier means comes from the client's catalog, which this module does not hold.

use std::io;

use prost::Message;

/// Decode one of this module's messages, reporting malformed input as `InvalidData`.
pub fn decode<M: Message + Default>(bytes: &[u8]) -> io::Result<M> {
    M::decode(bytes).map_err(|error| io::Error::new(io::ErrorKind::InvalidData, error))
}

/// Encode a message in field-number order, as the client writes it.
pub fn encode<M: Message>(message: &M) -> Vec<u8> {
    message.encode_to_vec()
}

/// `CGPerformTeamShuffleRule`
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, PartialOrd, Ord, prost::Enumeration)]
#[repr(i32)]
pub enum PerformTeamShuffleRule {
    EveryMatch = 1,
    OnMapFinish = 2,
    Never = 3,
}

/// `CGTeamShuffleRule`
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, PartialOrd, Ord, prost::Enumeration)]
#[repr(i32)]
pub enum TeamShuffleRule {
    Random = 1,
}

/// `CGNextMapRule`
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, PartialOrd, Ord, prost::Enumeration)]
#[repr(i32)]
pub enum NextMapRule {
    InOrder = 1,
    Random = 2,
    Calculate = 3,
}

/// `CGMapChangeRule`
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, PartialOrd, Ord, prost::Enumeration)]
#[repr(i32)]
pub enum MapChangeRule {
    EveryMap = 1,
    OnMapFinish = 2,
    Never = 3,
}

/// `CGBackToLobbyRule`
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, PartialOrd, Ord, prost::Enumeration)]
#[repr(i32)]
pub enum BackToLobbyRule {
    EveryMatch = 1,
    OnMapFinish = 2,
    Never = 3,
}

/// `CGGameRulesetVarValuePair`: one setting, as a variable GUID and the value kind it uses.
#[derive(Clone, PartialEq, Message)]
pub struct RulesetVarValuePair {
    #[prost(uint64, optional, tag = "1")]
    pub var_guid: Option<u64>,
    #[prost(int32, optional, tag = "2")]
    pub int_value: Option<i32>,
    #[prost(uint64, optional, tag = "3")]
    pub enum_guid_value: Option<u64>,
    #[prost(bool, optional, tag = "4")]
    pub bool_value: Option<bool>,
    #[prost(float, optional, tag = "5")]
    pub float_value: Option<f32>,
}

/// `CGGameRulesetBodyVars`: one hero's settings.
#[derive(Clone, PartialEq, Message)]
pub struct RulesetBodyVars {
    #[prost(message, repeated, tag = "1")]
    pub body_vars: Vec<RulesetVarValuePair>,
    #[prost(uint64, optional, tag = "2")]
    pub hero_guid: Option<u64>,
}

/// `CGGameRulesetTeam`
#[derive(Clone, PartialEq, Message)]
pub struct RulesetTeam {
    #[prost(uint32, optional, tag = "1")]
    pub team_index: Option<u32>,
    #[prost(uint32, optional, tag = "2")]
    pub num_team_members: Option<u32>,
    #[prost(bool, optional, tag = "3")]
    pub heroes_array_is_whitelist: Option<bool>,
    #[prost(uint64, repeated, packed = "false", tag = "4")]
    pub hero_guids: Vec<u64>,
    #[prost(message, repeated, tag = "5")]
    pub body_vars: Vec<RulesetBodyVars>,
    #[prost(message, repeated, tag = "6")]
    pub all_hero_body_vars: Vec<RulesetVarValuePair>,
    #[prost(message, repeated, tag = "7")]
    pub controller_vars: Vec<RulesetVarValuePair>,
}

/// `CGTeamRules`
#[derive(Clone, PartialEq, Message)]
pub struct TeamRules {
    #[prost(enumeration = "PerformTeamShuffleRule", optional, tag = "1")]
    pub perform_team_shuffle_rule: Option<i32>,
    #[prost(enumeration = "TeamShuffleRule", optional, tag = "2")]
    pub team_shuffle_rule: Option<i32>,
    #[prost(bool, optional, tag = "3")]
    pub swap_teams_if_no_shuffle: Option<bool>,
    #[prost(int32, optional, tag = "4")]
    pub max_observers: Option<i32>,
    #[prost(bool, optional, tag = "5")]
    pub pause_on_disconnect: Option<bool>,
}

/// `CGMapRules`
#[derive(Clone, PartialEq, Message)]
pub struct MapRules {
    #[prost(enumeration = "NextMapRule", optional, tag = "1")]
    pub next_map_rule: Option<i32>,
    #[prost(enumeration = "MapChangeRule", optional, tag = "2")]
    pub map_change_rule: Option<i32>,
    #[prost(enumeration = "BackToLobbyRule", optional, tag = "3")]
    pub back_to_lobby_rule: Option<i32>,
}

/// `PBCGLogicTarget`: a rule's event and the team, slot and hero it is limited to.
#[derive(Clone, PartialEq, Message)]
pub struct LogicTarget {
    #[prost(int32, optional, tag = "1")]
    pub r#type: Option<i32>,
    #[prost(int32, optional, tag = "2")]
    pub team: Option<i32>,
    #[prost(int32, optional, tag = "3")]
    pub slot: Option<i32>,
    #[prost(uint64, optional, tag = "4")]
    pub hero: Option<u64>,
}

/// `PBCGLogicParam`: one operand of a condition or an action.
#[derive(Clone, PartialEq, Message)]
pub struct LogicParam {
    #[prost(int32, optional, tag = "1")]
    pub enum_val: Option<i32>,
    #[prost(uint64, optional, tag = "2")]
    pub val: Option<u64>,
    #[prost(bool, optional, tag = "3")]
    pub is_var: Option<bool>,
    #[prost(bool, optional, tag = "4")]
    pub is_global_var: Option<bool>,
    #[prost(int32, optional, tag = "5")]
    pub value_identifier: Option<i32>,
    #[prost(int32, repeated, packed = "false", tag = "6")]
    pub unused_value_params: Vec<i32>,
    #[prost(uint64, repeated, packed = "false", tag = "7")]
    pub value_params: Vec<u64>,
    #[prost(string, optional, tag = "8")]
    pub value_str: Option<String>,
    #[prost(string, repeated, tag = "9")]
    pub value_strs: Vec<String>,
}

/// `PBCGLogicCondition`
#[derive(Clone, PartialEq, Message)]
pub struct LogicCondition {
    #[prost(bool, optional, tag = "1")]
    pub invert: Option<bool>,
    #[prost(int32, optional, tag = "2")]
    pub index: Option<i32>,
    #[prost(message, repeated, tag = "3")]
    pub params: Vec<LogicParam>,
    #[prost(bool, optional, tag = "4")]
    pub disabled: Option<bool>,
    #[prost(string, optional, tag = "5")]
    pub comment: Option<String>,
}

/// `PBCGLogicAction`
#[derive(Clone, PartialEq, Message)]
pub struct LogicAction {
    #[prost(int32, optional, tag = "1")]
    pub index: Option<i32>,
    #[prost(message, repeated, tag = "2")]
    pub params: Vec<LogicParam>,
    #[prost(bool, optional, tag = "3")]
    pub disabled: Option<bool>,
    #[prost(string, optional, tag = "4")]
    pub comment: Option<String>,
}

/// `PBCGLogicEntry`: one rule.
#[derive(Clone, PartialEq, Message)]
pub struct LogicEntry {
    #[prost(message, optional, tag = "1")]
    pub target: Option<LogicTarget>,
    #[prost(message, repeated, tag = "2")]
    pub conditions: Vec<LogicCondition>,
    #[prost(message, repeated, tag = "3")]
    pub actions: Vec<LogicAction>,
    #[prost(string, optional, tag = "4")]
    pub comment: Option<String>,
    #[prost(bool, optional, tag = "5")]
    pub disabled: Option<bool>,
}

/// `PBCGVec3`
#[derive(Clone, Copy, PartialEq, Message)]
pub struct Vec3 {
    #[prost(float, optional, tag = "1")]
    pub x: Option<f32>,
    #[prost(float, optional, tag = "2")]
    pub y: Option<f32>,
    #[prost(float, optional, tag = "3")]
    pub z: Option<f32>,
}

/// `PBCGEntityEntry`
#[derive(Clone, PartialEq, Message)]
pub struct EntityEntry {
    #[prost(int32, optional, tag = "1")]
    pub r#type: Option<i32>,
    #[prost(message, optional, tag = "2")]
    pub pos: Option<Vec3>,
    #[prost(message, optional, tag = "3")]
    pub facing: Option<Vec3>,
    #[prost(message, optional, tag = "4")]
    pub up: Option<Vec3>,
    #[prost(message, optional, tag = "5")]
    pub scale: Option<Vec3>,
}

/// `PBCGVariableEntry`
#[derive(Clone, PartialEq, Eq, Hash, Message)]
pub struct VariableEntry {
    #[prost(string, optional, tag = "1")]
    pub name: Option<String>,
}

/// `PBCGSubroutineEntry`
#[derive(Clone, PartialEq, Eq, Hash, Message)]
pub struct SubroutineEntry {
    #[prost(string, optional, tag = "1")]
    pub name: Option<String>,
}

/// `PBCGLogicUserSettingInst`: the value chosen for one Workshop setting.
#[derive(Clone, PartialEq, Message)]
pub struct UserSettingInst {
    #[prost(string, optional, tag = "1")]
    pub name: Option<String>,
    #[prost(int32, optional, tag = "2")]
    pub r#type: Option<i32>,
    #[prost(message, optional, tag = "3")]
    pub val: Option<Vec3>,
    #[prost(uint64, repeated, packed = "false", tag = "4")]
    pub hero_guids: Vec<u64>,
}

/// `PBCGLogic`: a Workshop script.
#[derive(Clone, PartialEq, Message)]
pub struct Logic {
    #[prost(uint32, optional, tag = "1")]
    pub dummy: Option<u32>,
    #[prost(message, repeated, tag = "2")]
    pub entries: Vec<LogicEntry>,
    #[prost(message, repeated, tag = "3")]
    pub entities: Vec<EntityEntry>,
    #[prost(message, repeated, tag = "4")]
    pub global_variables: Vec<VariableEntry>,
    #[prost(message, repeated, tag = "5")]
    pub player_variables: Vec<VariableEntry>,
    #[prost(message, repeated, tag = "6")]
    pub subroutines: Vec<SubroutineEntry>,
    #[prost(message, repeated, tag = "7")]
    pub user_setting_insts: Vec<UserSettingInst>,
    #[prost(uint32, repeated, packed = "false", tag = "8")]
    pub extensions: Vec<u32>,
}

impl Logic {
    /// The rules that are not disabled, in script order.
    pub fn enabled_entries(&self) -> impl Iterator<Item = &LogicEntry> {
        self.entries
            .iter()
            .filter(|entry| entry.disabled != Some(true))
    }
}

impl LogicEntry {
    /// The conditions that are not disabled, in rule order.
    pub fn enabled_conditions(&self) -> impl Iterator<Item = &LogicCondition> {
        self.conditions
            .iter()
            .filter(|condition| condition.disabled != Some(true))
    }

    /// The actions that are not disabled, in rule order.
    pub fn enabled_actions(&self) -> impl Iterator<Item = &LogicAction> {
        self.actions
            .iter()
            .filter(|action| action.disabled != Some(true))
    }
}

/// `CGGameRuleset`: one game mode's settings and its script.
#[derive(Clone, PartialEq, Message)]
pub struct GameRuleset {
    #[prost(uint64, optional, tag = "1")]
    pub game_mode_guid: Option<u64>,
    #[prost(uint64, optional, tag = "2")]
    pub game_ruleset_guid: Option<u64>,
    #[prost(message, repeated, tag = "3")]
    pub master_vars: Vec<RulesetVarValuePair>,
    #[prost(message, repeated, tag = "4")]
    pub global_admin_vars: Vec<RulesetVarValuePair>,
    #[prost(message, repeated, tag = "5")]
    pub teams: Vec<RulesetTeam>,
    #[prost(uint32, optional, tag = "6")]
    pub flags: Option<u32>,
    #[prost(message, optional, tag = "7")]
    pub logic: Option<Logic>,
    #[prost(string, optional, tag = "8")]
    pub logic_str: Option<String>,
}

/// `CGGameRulesetMapPair`
#[derive(Clone, PartialEq, Eq, Hash, Message)]
pub struct RulesetMapPair {
    #[prost(uint64, optional, tag = "1")]
    pub map_guid: Option<u64>,
    #[prost(int32, optional, tag = "2")]
    pub saved_game_index: Option<i32>,
    #[prost(bool, optional, tag = "3")]
    pub is_ruleset_cleared: Option<bool>,
}

/// `CGPlayerID`
#[derive(Clone, Copy, PartialEq, Eq, Hash, Message)]
pub struct PlayerId {
    #[prost(uint64, optional, tag = "1")]
    pub src: Option<u64>,
    #[prost(uint64, optional, tag = "2")]
    pub seq: Option<u64>,
}

/// `CGLinkIdentity`: the title, share code and creator of a shared custom game.
#[derive(Clone, PartialEq, Eq, Hash, Message)]
pub struct LinkIdentity {
    #[prost(string, optional, tag = "1")]
    pub game_title: Option<String>,
    #[prost(string, optional, tag = "2")]
    pub code: Option<String>,
    #[prost(message, optional, tag = "3")]
    pub creator_id: Option<PlayerId>,
    #[prost(message, optional, tag = "4")]
    pub creator_secondary_account_id: Option<PlayerId>,
    #[prost(int32, optional, tag = "5")]
    pub creator_platform: Option<i32>,
    #[prost(uint64, optional, tag = "6")]
    pub hash: Option<u64>,
    #[prost(uint64, optional, tag = "7")]
    pub avatar_portrait: Option<u64>,
    #[prost(uint64, optional, tag = "8")]
    pub portrait_frame: Option<u64>,
    #[prost(uint64, optional, tag = "9")]
    pub timestamp_secs: Option<u64>,
    #[prost(int32, optional, tag = "10")]
    pub level: Option<i32>,
}

/// `CGOptions`: a whole custom game. The schema has no field 12.
#[derive(Clone, PartialEq, Message)]
pub struct Options {
    #[prost(message, optional, tag = "1")]
    pub map_rules: Option<MapRules>,
    #[prost(message, optional, tag = "2")]
    pub team_rules: Option<TeamRules>,
    #[prost(message, repeated, tag = "3")]
    pub ruleset_map_pairs: Vec<RulesetMapPair>,
    #[prost(message, repeated, tag = "4")]
    pub saved_game_rulesets: Vec<GameRuleset>,
    #[prost(bool, optional, tag = "5")]
    pub match_voice_chat_enabled: Option<bool>,
    /// Marked deprecated in the schema; `datacenter_override_str` replaces it.
    #[prost(uint32, optional, tag = "6")]
    pub datacenter_override: Option<u32>,
    #[prost(string, optional, tag = "7")]
    pub description: Option<String>,
    #[prost(message, optional, tag = "8")]
    pub root_logic: Option<Logic>,
    #[prost(uint64, optional, tag = "9")]
    pub difficulty_guid: Option<u64>,
    #[prost(bool, optional, tag = "10")]
    pub allow_skirmishers: Option<bool>,
    #[prost(bool, optional, tag = "11")]
    pub use_balance_test_if_available: Option<bool>,
    #[prost(int64, optional, tag = "13")]
    pub minimum_latency_ns: Option<i64>,
    #[prost(message, optional, tag = "14")]
    pub link_identity: Option<LinkIdentity>,
    #[prost(string, optional, tag = "15")]
    pub datacenter_override_str: Option<String>,
}

/// `PersistedCGSettings`: custom game settings saved with a format version.
#[derive(Clone, PartialEq, Message)]
pub struct PersistedSettings {
    #[prost(int32, optional, tag = "1")]
    pub version: Option<i32>,
    #[prost(message, optional, tag = "2")]
    pub options: Option<Options>,
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sample_logic() -> Logic {
        Logic {
            entries: vec![
                LogicEntry {
                    target: Some(LogicTarget {
                        r#type: Some(1),
                        team: Some(2),
                        ..Default::default()
                    }),
                    conditions: vec![LogicCondition {
                        invert: Some(true),
                        index: Some(4),
                        params: vec![
                            LogicParam {
                                value_identifier: Some(17),
                                ..Default::default()
                            },
                            LogicParam {
                                enum_val: Some(3),
                                ..Default::default()
                            },
                        ],
                        ..Default::default()
                    }],
                    actions: vec![
                        LogicAction {
                            index: Some(9),
                            params: vec![LogicParam {
                                value_identifier: Some(40),
                                value_params: vec![1, 2],
                                value_str: Some("Hello".to_owned()),
                                value_strs: vec!["a".to_owned(), "b".to_owned()],
                                ..Default::default()
                            }],
                            comment: Some("greet".to_owned()),
                            ..Default::default()
                        },
                        LogicAction {
                            index: Some(2),
                            disabled: Some(true),
                            ..Default::default()
                        },
                    ],
                    comment: Some("first rule".to_owned()),
                    ..Default::default()
                },
                LogicEntry {
                    disabled: Some(true),
                    ..Default::default()
                },
            ],
            entities: vec![EntityEntry {
                r#type: Some(1),
                pos: Some(Vec3 {
                    x: Some(1.0),
                    y: Some(2.5),
                    z: Some(-3.0),
                }),
                ..Default::default()
            }],
            global_variables: vec![VariableEntry {
                name: Some("score".to_owned()),
            }],
            player_variables: vec![VariableEntry {
                name: Some("lives".to_owned()),
            }],
            subroutines: vec![SubroutineEntry {
                name: Some("reset".to_owned()),
            }],
            user_setting_insts: vec![UserSettingInst {
                name: Some("Speed".to_owned()),
                r#type: Some(2),
                val: Some(Vec3 {
                    x: Some(150.0),
                    ..Default::default()
                }),
                hero_guids: vec![0x02e0_0000_0000_012f],
            }],
            extensions: vec![3, 5],
            ..Default::default()
        }
    }

    #[test]
    fn action_matches_hand_written_wire_bytes() {
        // index = 5 (field 1 varint), disabled = true (field 3 varint), comment = "hi" (field 4).
        let bytes = [0x08, 0x05, 0x18, 0x01, 0x22, 0x02, b'h', b'i'];
        let action: LogicAction = decode(&bytes).unwrap();
        assert_eq!(action.index, Some(5));
        assert_eq!(action.disabled, Some(true));
        assert_eq!(action.comment.as_deref(), Some("hi"));
        assert!(action.params.is_empty());
        assert_eq!(encode(&action), bytes);
    }

    #[test]
    fn repeated_scalars_are_not_packed() {
        let param = LogicParam {
            unused_value_params: vec![7],
            value_params: vec![1, 300],
            ..Default::default()
        };
        // Field 6 varint 7, then field 7 once per value: 1 and 300 (0xAC 0x02).
        assert_eq!(encode(&param), [0x30, 0x07, 0x38, 0x01, 0x38, 0xac, 0x02]);
        let team = RulesetTeam {
            hero_guids: vec![2, 3],
            ..Default::default()
        };
        assert_eq!(encode(&team), [0x20, 0x02, 0x20, 0x03]);
        let logic = Logic {
            extensions: vec![4, 4],
            ..Default::default()
        };
        assert_eq!(encode(&logic), [0x40, 0x04, 0x40, 0x04]);
    }

    #[test]
    fn presence_survives_zero_and_false_values() {
        let pair = RulesetVarValuePair {
            var_guid: Some(0),
            int_value: Some(0),
            bool_value: Some(false),
            float_value: Some(0.0),
            ..Default::default()
        };
        let bytes = encode(&pair);
        assert_eq!(
            bytes,
            [0x08, 0x00, 0x10, 0x00, 0x20, 0x00, 0x2d, 0, 0, 0, 0]
        );
        assert_eq!(decode::<RulesetVarValuePair>(&bytes).unwrap(), pair);
        assert!(encode(&RulesetVarValuePair::default()).is_empty());
    }

    #[test]
    fn whole_custom_game_round_trips() {
        let options = Options {
            map_rules: Some(MapRules {
                next_map_rule: Some(NextMapRule::Random as i32),
                map_change_rule: Some(MapChangeRule::Never as i32),
                back_to_lobby_rule: Some(BackToLobbyRule::OnMapFinish as i32),
            }),
            team_rules: Some(TeamRules {
                perform_team_shuffle_rule: Some(PerformTeamShuffleRule::Never as i32),
                team_shuffle_rule: Some(TeamShuffleRule::Random as i32),
                max_observers: Some(2),
                ..Default::default()
            }),
            ruleset_map_pairs: vec![RulesetMapPair {
                map_guid: Some(0x0688),
                saved_game_index: Some(0),
                is_ruleset_cleared: Some(false),
            }],
            saved_game_rulesets: vec![GameRuleset {
                game_mode_guid: Some(0x20),
                master_vars: vec![RulesetVarValuePair {
                    var_guid: Some(1),
                    float_value: Some(1.5),
                    ..Default::default()
                }],
                teams: vec![RulesetTeam {
                    team_index: Some(1),
                    num_team_members: Some(6),
                    heroes_array_is_whitelist: Some(true),
                    hero_guids: vec![0x02e0_0000_0000_012f],
                    body_vars: vec![RulesetBodyVars {
                        hero_guid: Some(0x02e0_0000_0000_012f),
                        body_vars: vec![RulesetVarValuePair {
                            var_guid: Some(9),
                            int_value: Some(200),
                            ..Default::default()
                        }],
                    }],
                    ..Default::default()
                }],
                flags: Some(1),
                logic: Some(sample_logic()),
                logic_str: Some("rule(\"first rule\") {}".to_owned()),
                ..Default::default()
            }],
            description: Some("test mode".to_owned()),
            root_logic: Some(sample_logic()),
            minimum_latency_ns: Some(-1),
            link_identity: Some(LinkIdentity {
                game_title: Some("Test".to_owned()),
                code: Some("ABCDE".to_owned()),
                creator_id: Some(PlayerId {
                    src: Some(1),
                    seq: Some(2),
                }),
                level: Some(10),
                ..Default::default()
            }),
            datacenter_override_str: Some("local".to_owned()),
            ..Default::default()
        };
        let persisted = PersistedSettings {
            version: Some(3),
            options: Some(options),
        };
        let bytes = encode(&persisted);
        let decoded: PersistedSettings = decode(&bytes).unwrap();
        assert_eq!(decoded, persisted);
        assert_eq!(encode(&decoded), bytes);

        let options = decoded.options.unwrap();
        let rules = options.map_rules.as_ref().unwrap();
        assert_eq!(rules.next_map_rule(), NextMapRule::Random);
        assert_eq!(rules.map_change_rule(), MapChangeRule::Never);
        let logic = options.saved_game_rulesets[0].logic.as_ref().unwrap();
        assert_eq!(logic.enabled_entries().count(), 1);
        let rule = logic.enabled_entries().next().unwrap();
        assert_eq!(rule.enabled_conditions().count(), 1);
        assert_eq!(
            rule.enabled_actions()
                .map(|action| action.index)
                .collect::<Vec<_>>(),
            [Some(9)]
        );
    }

    #[test]
    fn unknown_fields_are_skipped_and_damage_is_reported() {
        // Field 12 does not exist in CGOptions; description (field 7) follows it.
        let bytes = [0x60, 0x01, 0x3a, 0x01, b'x'];
        let options: Options = decode(&bytes).unwrap();
        assert_eq!(options.description.as_deref(), Some("x"));
        assert_eq!(encode(&options), [0x3a, 0x01, b'x']);

        // A string of length 5 with one byte of content.
        let error = decode::<Options>(&[0x3a, 0x05, b'x']).unwrap_err();
        assert_eq!(error.kind(), io::ErrorKind::InvalidData);
    }

    /// Fills every field of every message from the client's own descriptor, then checks that the
    /// types above read and write the same bytes. `tools/extract_custom_game_descriptor.py` writes
    /// the descriptor from a local 104319 client; name its path in ORPHEUS_CUSTOM_GAME_DESCRIPTOR.
    #[test]
    #[ignore = "requires the locally extracted 104319 CustomGame descriptor"]
    fn every_message_matches_the_client_descriptor() {
        use prost_reflect::{DescriptorPool, DynamicMessage, Kind, MessageDescriptor, Value};

        fn sample(kind: &Kind, seed: u32) -> Value {
            match kind {
                Kind::Double => Value::F64(f64::from(seed) + 0.5),
                Kind::Float => Value::F32(seed as f32 + 0.25),
                Kind::Int32 | Kind::Sint32 | Kind::Sfixed32 => Value::I32(seed as i32 + 1),
                Kind::Int64 | Kind::Sint64 | Kind::Sfixed64 => Value::I64(i64::from(seed) + 1),
                Kind::Uint32 | Kind::Fixed32 => Value::U32(seed + 1),
                Kind::Uint64 | Kind::Fixed64 => Value::U64(u64::from(seed) + 0x1_0000_0001),
                Kind::Bool => Value::Bool(true),
                Kind::String => Value::String(format!("s{seed}")),
                Kind::Bytes => Value::Bytes(vec![seed as u8].into()),
                Kind::Message(message) => Value::Message(filled(message)),
                Kind::Enum(values) => {
                    Value::EnumNumber(values.values().last().expect("an enum value").number())
                }
            }
        }

        fn filled(descriptor: &MessageDescriptor) -> DynamicMessage {
            let mut message = DynamicMessage::new(descriptor.clone());
            for field in descriptor.fields() {
                let kind = field.kind();
                let value = if field.is_list() {
                    Value::List(vec![
                        sample(&kind, field.number()),
                        sample(&kind, field.number() + 7),
                    ])
                } else {
                    sample(&kind, field.number())
                };
                message.set_field(&field, value);
            }
            message
        }

        fn through<M: Message + Default>(bytes: &[u8]) -> Vec<u8> {
            encode(&decode::<M>(bytes).unwrap())
        }

        let path = std::env::var_os("ORPHEUS_CUSTOM_GAME_DESCRIPTOR")
            .expect("set ORPHEUS_CUSTOM_GAME_DESCRIPTOR");
        let mut pool = DescriptorPool::new();
        pool.decode_file_descriptor_proto(std::fs::read(path).unwrap().as_slice())
            .unwrap();

        type Through = fn(&[u8]) -> Vec<u8>;
        let known: [(&str, Through); 22] = [
            ("CGGameRulesetBodyVars", through::<RulesetBodyVars>),
            ("CGGameRulesetVarValuePair", through::<RulesetVarValuePair>),
            ("CGGameRulesetTeam", through::<RulesetTeam>),
            ("CGTeamRules", through::<TeamRules>),
            ("CGMapRules", through::<MapRules>),
            ("PBCGLogicTarget", through::<LogicTarget>),
            ("PBCGLogicParam", through::<LogicParam>),
            ("PBCGLogicCondition", through::<LogicCondition>),
            ("PBCGLogicAction", through::<LogicAction>),
            ("PBCGLogicEntry", through::<LogicEntry>),
            ("PBCGVec3", through::<Vec3>),
            ("PBCGEntityEntry", through::<EntityEntry>),
            ("PBCGVariableEntry", through::<VariableEntry>),
            ("PBCGSubroutineEntry", through::<SubroutineEntry>),
            ("PBCGLogicUserSettingInst", through::<UserSettingInst>),
            ("PBCGLogic", through::<Logic>),
            ("CGGameRuleset", through::<GameRuleset>),
            ("CGGameRulesetMapPair", through::<RulesetMapPair>),
            ("CGPlayerID", through::<PlayerId>),
            ("CGLinkIdentity", through::<LinkIdentity>),
            ("CGOptions", through::<Options>),
            ("PersistedCGSettings", through::<PersistedSettings>),
        ];
        let mut names: Vec<String> = pool
            .all_messages()
            .map(|message| message.full_name().to_owned())
            .collect();
        names.sort();
        let mut expected: Vec<&str> = known.iter().map(|(name, _)| *name).collect();
        expected.sort_unstable();
        assert_eq!(names, expected);

        for (name, through) in known {
            let descriptor = pool.get_message_by_name(name).unwrap();
            let bytes = filled(&descriptor).encode_to_vec();
            assert!(!bytes.is_empty(), "{name}");
            assert_eq!(through(&bytes), bytes, "{name}");
        }
    }
}
