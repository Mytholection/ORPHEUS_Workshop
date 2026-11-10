"""The custom game descriptor is found inside a client image and cut at its own end."""

import sys
import tempfile
import unittest
from pathlib import Path

from google.protobuf import descriptor_pb2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import extract_custom_game_descriptor as tool


def synthetic_descriptor() -> bytes:
    """A small stand-in with the client's file name: one message, one enum."""
    file = descriptor_pb2.FileDescriptorProto(name=tool.PROTO_NAME.decode())
    message = file.message_type.add(name="Rule")
    message.field.add(name="index", number=1, label=1, type=5)
    message.field.add(name="params", number=2, label=3, type=11, type_name=".Rule")
    message.field.add(name="mode", number=3, label=1, type=14, type_name=".Mode")
    enum = file.enum_type.add(name="Mode")
    enum.value.add(name="First", number=1)
    enum.value.add(name="Second", number=2)
    return file.SerializeToString()


class TestFindDescriptor(unittest.TestCase):
    def test_descriptor_is_cut_out_of_surrounding_bytes(self):
        descriptor = synthetic_descriptor()
        for tail in (b"\x00" * 16, b"\x0a\x03abc" + b"\xff" * 8, b""):
            image = b"MZ" + b"\x90" * 64 + descriptor + tail
            self.assertEqual(tool.find_descriptor(image), descriptor, tail)

    def test_missing_and_damaged_descriptors_are_reported(self):
        with self.assertRaises(tool.ExtractError):
            tool.find_descriptor(b"no descriptor here")
        descriptor = synthetic_descriptor()
        name_only = descriptor[: len(tool.PROTO_NAME) + 2]
        with self.assertRaises(tool.ExtractError):
            tool.find_descriptor(name_only + b"\xff\xff\xff")

    def test_text_lists_messages_fields_and_enums(self):
        text = tool.describe(synthetic_descriptor())
        self.assertIn("message Rule\n", text)
        self.assertIn("    1 optional int32 index\n", text)
        self.assertIn("    2 repeated Rule params\n", text)
        self.assertIn("    3 optional Mode mode\n", text)
        self.assertIn("enum Mode: First=1, Second=2\n", text)

    def test_command_writes_the_descriptor_and_its_text(self):
        descriptor = synthetic_descriptor()
        with tempfile.TemporaryDirectory() as folder:
            game = Path(folder) / "Overwatch.exe"
            game.write_bytes(b"\x00" * 32 + descriptor + b"\x00" * 32)
            output, text = Path(folder) / "descriptor.bin", Path(folder) / "descriptor.txt"
            code = tool.main(["--game", str(game), "--output", str(output), "--text", str(text)])
            self.assertEqual(code, 0)
            self.assertEqual(output.read_bytes(), descriptor)
            self.assertIn("message Rule", text.read_text(encoding="utf-8"))
            absent = Path(folder) / "absent.exe"
            self.assertEqual(tool.main(["--game", str(absent), "--output", str(output)]), 1)


if __name__ == "__main__":
    unittest.main()
