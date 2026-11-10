"""Write the custom game protobuf descriptor that the 1.74 client embeds (build 104319).

The client carries the serialized FileDescriptorProto of game/Core/Utilities/Protobuf/CustomGame.proto:
custom game settings and Workshop scripts (CGOptions, CGGameRuleset, PBCGLogic and their parts).
rust/src/custom_game_proto.rs mirrors those messages; its ignored test reads this tool's output from
the path in ORPHEUS_CUSTOM_GAME_DESCRIPTOR and checks every message against it.

    py tools/extract_custom_game_descriptor.py --game <Overwatch.exe> --output <file> [--text <file>]

The descriptor is client data: keep the output outside the repository. --text also writes the messages
and their fields as plain text.
"""

import argparse
import sys
from pathlib import Path

from google.protobuf import descriptor_pb2
from google.protobuf.message import DecodeError

PROTO_NAME = b"game/Core/Utilities/Protobuf/CustomGame.proto"
MAX_SIZE = 64 * 1024  # far above the 104319 descriptor (3802 bytes)

LABELS = {1: "optional", 2: "required", 3: "repeated"}
SCALARS = {
    1: "double", 2: "float", 3: "int64", 4: "uint64", 5: "int32", 6: "fixed64", 7: "fixed32", 8: "bool",
    9: "string", 12: "bytes", 13: "uint32", 15: "sfixed32", 16: "sfixed64", 17: "sint32", 18: "sint64",
}  # fmt: skip


class ExtractError(ValueError):
    pass


def find_descriptor(image: bytes) -> bytes:
    """The serialized descriptor in a client image: it starts with its own name as field 1."""
    start = image.find(b"\x0a" + bytes([len(PROTO_NAME)]) + PROTO_NAME)
    if start < 0:
        raise ExtractError("the image does not contain the CustomGame.proto descriptor")
    best = b""
    for end in range(start + len(PROTO_NAME) + 2, min(len(image), start + MAX_SIZE) + 1):
        candidate = image[start:end]
        try:
            parsed = descriptor_pb2.FileDescriptorProto.FromString(candidate)
        except DecodeError:
            continue
        # The bytes after the descriptor are not part of it: keep the longest prefix that is exactly
        # one descriptor (it serializes back to itself) and declares messages.
        if parsed.message_type and parsed.SerializeToString() == candidate:
            best = candidate
    if not best:
        raise ExtractError("the CustomGame.proto descriptor is damaged or cut short")
    return best


def describe(descriptor: bytes) -> str:
    """The messages, fields and enums of a descriptor, one per line."""
    parsed = descriptor_pb2.FileDescriptorProto.FromString(descriptor)
    lines = []
    for message in parsed.message_type:
        lines.append(f"message {message.name}")
        for field in message.field:
            kind = field.type_name.lstrip(".") or SCALARS.get(field.type, str(field.type))
            lines.append(f"  {field.number:3} {LABELS[field.label]} {kind} {field.name}")
    for enum in parsed.enum_type:
        values = ", ".join(f"{value.name}={value.number}" for value in enum.value)
        lines.append(f"enum {enum.name}: {values}")
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--game", type=Path, required=True, help="the 104319 Overwatch.exe")
    parser.add_argument("--output", type=Path, required=True, help="where to write the descriptor")
    parser.add_argument("--text", type=Path, help="also write the messages and fields as text")
    args = parser.parse_args(argv)
    try:
        descriptor = find_descriptor(args.game.read_bytes())
    except (OSError, ExtractError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    args.output.write_bytes(descriptor)
    if args.text:
        args.text.write_text(describe(descriptor), encoding="utf-8")
    parsed = descriptor_pb2.FileDescriptorProto.FromString(descriptor)
    print(f"{len(descriptor)} bytes, {len(parsed.message_type)} messages, {len(parsed.enum_type)} enums")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
