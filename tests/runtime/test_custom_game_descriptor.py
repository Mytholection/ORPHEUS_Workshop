"""The custom game schema in ow174.workshop.messages against the client's own descriptor.

tools/extract_custom_game_descriptor.py writes the descriptor from a local 104319 client. Name its
path in ORPHEUS_CUSTOM_GAME_DESCRIPTOR; without it the comparison is skipped.
"""

import os
import sys
import unittest
from pathlib import Path

from google.protobuf import descriptor_pb2

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ow174.workshop import messages

DESCRIPTOR = os.environ.get("ORPHEUS_CUSTOM_GAME_DESCRIPTOR")


def shape(file: descriptor_pb2.FileDescriptorProto) -> dict:
    """What decides the wire form and the names: every message's fields and every enum's values."""
    return {
        "name": file.name,
        "package": file.package,
        "messages": {
            message.name: [
                (field.number, field.name, field.type, field.label, field.type_name)
                for field in message.field
            ]
            for message in file.message_type
        },
        "enums": {enum.name: [(value.name, value.number) for value in enum.value] for enum in file.enum_type},
    }


@unittest.skipUnless(DESCRIPTOR, "requires the locally extracted 104319 CustomGame descriptor")
class ClientDescriptorTests(unittest.TestCase):
    def setUp(self):
        self.client = descriptor_pb2.FileDescriptorProto.FromString(Path(DESCRIPTOR).read_bytes())

    def test_schema_matches_the_client_descriptor(self):
        ours, theirs = shape(messages.file_descriptor()), shape(self.client)
        self.assertEqual(list(ours["messages"]), list(theirs["messages"]))
        for name, fields in theirs["messages"].items():
            self.assertEqual(ours["messages"][name], fields, name)
        self.assertEqual(ours["enums"], theirs["enums"])
        self.assertEqual((ours["name"], ours["package"]), (theirs["name"], theirs["package"]))

    def test_client_descriptor_has_no_shapes_the_schema_cannot_express(self):
        self.assertEqual(self.client.syntax, "")
        self.assertEqual(list(self.client.dependency), [])
        for message in self.client.message_type:
            extras = message.nested_type or message.oneof_decl or message.extension_range
            self.assertFalse(extras, message.name)
            for field in message.field:
                self.assertFalse(field.options.packed, f"{message.name}.{field.name}")
                self.assertEqual(field.default_value, "", f"{message.name}.{field.name}")


if __name__ == "__main__":
    unittest.main()
