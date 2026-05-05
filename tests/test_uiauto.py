from pathlib import Path

from phone2app.uiauto import node_matches, parse_bounds, parse_ui_nodes


def test_parse_bounds():
    assert parse_bounds("[10,20][30,40]") == (10, 20, 30, 40)


def test_parse_ui_nodes_and_match(tmp_path: Path):
    xml = tmp_path / "window.xml"
    xml.write_text(
        """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="0">
  <node text="AI创作" resource-id="" class="android.widget.ImageView" package="x" content-desc="" clickable="true" bounds="[627,1083][869,1174]" />
</hierarchy>
""",
        encoding="utf-8",
    )
    nodes = parse_ui_nodes(xml)
    assert nodes[0].center == (748, 1128)
    assert node_matches(nodes[0], {"text": "AI创作"})
    assert node_matches(nodes[0], {"text_contains": "创作"})
