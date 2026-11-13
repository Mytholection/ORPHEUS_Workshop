"""The shared custom game message contract, read through the production decoder and encoder."""

import json
import os
import unittest
from pathlib import Path

from ow174.workshop.messages import CustomGameError, decode, encode, to_plain

FIXTURES = Path(
    os.environ.get("ORPHEUS_BEHAVIOR_FIXTURES")
    or Path(__file__).resolve().parents[2] / "fixtures/behavior"
)


class CustomGameMessageContractTests(unittest.TestCase):
    def setUp(self):
        self.contract = json.loads((FIXTURES / "custom-game-messages-v1.json").read_text(encoding="utf-8"))
        self.assertEqual(self.contract["schema_version"], 1)
        self.assertEqual(self.contract["case_id"], "custom-game-messages.synthetic-wire.v1")
        self.assertEqual(self.contract["target_build"], 104319)
        self.assertEqual(self.contract["evidence"], "synthetic-reference")
        self.cases = self.contract["input"]["cases"]
        self.expected = self.contract["expected"]

    def test_every_case_has_one_expected_result(self):
        self.assertEqual([case["id"] for case in self.cases], list(self.expected))
        self.assertEqual(len(self.cases), 7)

    def test_decoder_matches_shared_fields_and_errors(self):
        for case in self.cases:
            expected = self.expected[case["id"]]
            wire = bytes.fromhex(case["wire_hex"])
            with self.subTest(case=case["id"]):
                if "error" in expected:
                    self.assertEqual(expected["error"], "damaged")
                    with self.assertRaises(CustomGameError):
                        decode(case["message"], wire)
                else:
                    self.assertEqual(to_plain(decode(case["message"], wire)), expected["fields"])

    def test_encoder_matches_shared_wire_bytes(self):
        checked = 0
        for case in self.cases:
            expected = self.expected[case["id"]]
            if "encoded_hex" not in expected:
                continue  # an error, or a message whose unknown fields an encoder may keep or drop
            with self.subTest(case=case["id"]):
                message = decode(case["message"], bytes.fromhex(case["wire_hex"]))
                self.assertEqual(encode(message).hex(), expected["encoded_hex"])
                checked += 1
        self.assertEqual(checked, 5)


if __name__ == "__main__":
    unittest.main()
