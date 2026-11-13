"""The Workshop graph bundle keeps catalog order, follows graph references and names what is missing."""

import gzip
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ow174.game.script.graph import Graph
from tools import extract_workshop_graphs as tool
from tools.extract_game_graphs import EnumTables

NODE = 'm_602E1F8F="-1" m_26B6454C="{null}" m_2BBEEAB8="0" m_clientOnly="0" m_serverOnly="0"'
# Entry -> a node of class LAST. HELPERS adds graph references to the last node.
ACTION = '''<STUStatescriptGraph xmlns:dragon="https://yretenai.com/dragonml/v1"
    xmlns:tank="https://yretenai.com/dragonml/v1" m_nodesBitCount="2" m_statesBitCount="1">
  <STUGraph dragon:name="m_graph">
    <dragon:array dragon:name="m_items">
      <STUStatescriptEntry dragon:id="1" m_871A8203="0" m_ADEB6E05="0" m_uniqueID="1" NODE>
        <STUStatescriptOutputPlug dragon:id="2" dragon:name="m_outPlug">
          <dragon:array dragon:name="m_links">
            <STUGraphLink dragon:id="3">
              <dragon:ref dragon:id="2" dragon:name="m_outputPlug" />
              <STUStatescriptInputPlug dragon:id="4" dragon:name="m_inputPlug" m_links="{null}">
                <LAST dragon:id="5" dragon:name="m_parentNode" m_871A8203="1" m_ADEB6E05="1"
                    m_uniqueID="2" NODE>
                  <STUStatescriptOutputPlug dragon:id="6" dragon:name="m_outPlug" m_links="{null}"
                      m_parentNode="{null}" />
                  <dragon:ref dragon:id="4" dragon:name="m_inPlug" />
                  HELPERS
                </LAST>
              </STUStatescriptInputPlug>
            </STUGraphLink>
          </dragon:array>
          <dragon:ref dragon:id="1" dragon:name="m_parentNode" />
        </STUStatescriptOutputPlug>
      </STUStatescriptEntry>
      <dragon:ref dragon:id="5" />
    </dragon:array>
  </STUGraph>
  <dragon:array dragon:name="m_nodes"><dragon:ref dragon:id="1" /><dragon:ref dragon:id="5" /></dragon:array>
  <dragon:array dragon:name="m_states" />
  <dragon:array dragon:name="m_entries"><dragon:ref dragon:id="1" /></dragon:array>
  <dragon:array dragon:name="m_remoteSyncNodes" />
  <dragon:array dragon:name="m_syncVars" />
</STUStatescriptGraph>'''
CATALOG = {
    "Events": [{"DisplayName": "Ongoing - Global"}],
    "Actions": [
        {"DisplayName": "First", "GraphId": "000000000010.01B"},
        {"DisplayName": "No Graph", "GraphId": None},
        {"DisplayName": "Not Dumped", "GraphId": "000000000030.01B"},
    ],
    "Unknown": [{"DisplayName": "Comparison", "GraphId": "000000000011.01B"}],
}


def graph_xml(last="STU_1E93FE1F", helpers=()):
    refs = "".join(
        f'<tank:ref dragon:name="m_{number}" GUID="{guid}" />' for number, guid in enumerate(helpers)
    )
    return ACTION.replace("LAST", last).replace("HELPERS", refs).replace("NODE", NODE)


class WorkshopGraphBundleTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.xml = self.root / "01B"
        self.xml.mkdir()
        helpers = ("000000000020.01B", "000000000040.01B")
        (self.xml / "000000000010.01B.xml").write_text(graph_xml(helpers=helpers), encoding="utf-8")
        (self.xml / "000000000011.01B.xml").write_text(graph_xml(), encoding="utf-8")
        helper = graph_xml("STUStatescriptActionSetVar")
        (self.xml / "000000000020.01B.xml").write_text(helper, encoding="utf-8")
        self.catalog = self.root / "workshop.json"
        self.catalog.write_text("﻿" + json.dumps(CATALOG), encoding="utf-8")

    def test_bundle_keeps_catalog_order_and_follows_references(self):
        bundle, problems = tool.collect(CATALOG, self.xml, EnumTables(self.root))
        self.assertEqual(problems, {})
        self.assertEqual(bundle["workshop"]["actions"], [
            {"name": "First", "graph": 0x10},
            {"name": "No Graph", "graph": None},
            {"name": "Not Dumped", "graph": 0x30},
        ])
        self.assertEqual(bundle["workshop"]["conditions"], [{"name": "Comparison", "graph": 0x11}])
        self.assertEqual([record["index"] for record in bundle["graphs"]], [0x10, 0x11, 0x20])
        self.assertEqual(bundle["roots"]["graphs"], [0x10, 0x11, 0x30])
        self.assertEqual(bundle["missing"], [0x30, 0x40])

    def test_records_load_as_runtime_graphs(self):
        bundle, _ = tool.collect(CATALOG, self.xml, EnumTables(self.root))
        model = Graph(bundle["graphs"][0])
        self.assertEqual([node.cls for node in model.nodes], ["STUStatescriptEntry", "STU_1E93FE1F"])
        self.assertEqual(model.entries[0].links("m_outPlug"), [(1, "m_inPlug")])
        self.assertEqual(model.graph_refs(), {0x20, 0x40})

    def test_command_writes_the_bundle_outside_the_repository(self):
        output = self.root / "out" / "workshop_action_graphs.json.gz"
        arguments = ["--catalog", str(self.catalog), "--xml", str(self.xml), "--owlib", str(self.root)]
        report = io.StringIO()
        with redirect_stdout(report):
            self.assertEqual(tool.main([*arguments, "--output", str(output)]), 0)
        data = json.loads(gzip.decompress(output.read_bytes()))
        self.assertEqual(len(data["graphs"]), 3)
        self.assertIn("3 actions, 2 with a graph; 3 graphs", report.getvalue())
        self.assertIn("named but not in the dump: 0030 0040", report.getvalue())
        inside = tool.ROOT / "data" / "workshop_action_graphs.json.gz"
        with redirect_stderr(io.StringIO()) as error, self.assertRaises(SystemExit):
            tool.main([*arguments, "--output", str(inside)])
        self.assertIn("outside the repository", error.getvalue())
        self.assertFalse(inside.exists())

    def test_catalog_without_actions_is_refused(self):
        self.catalog.write_text(json.dumps({"Events": []}), encoding="utf-8")
        arguments = ["--catalog", str(self.catalog), "--xml", str(self.xml), "--owlib", str(self.root)]
        with redirect_stderr(io.StringIO()) as error, self.assertRaises(SystemExit):
            tool.main([*arguments, "--output", str(self.root / "bundle.json.gz")])
        self.assertIn("no Actions list", error.getvalue())


if __name__ == "__main__":
    unittest.main()
