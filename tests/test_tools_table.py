"""Le tableau des outils du README doit correspondre exactement a list_tools()."""
import asyncio
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import server  # noqa: E402


def test_readme_tools_match_server():
    names = sorted(t.name for t in asyncio.run(server.list_tools()))
    doc = (ROOT / "README.md").read_text(encoding="utf-8")
    block = doc[doc.index("<!-- tools:start -->"):doc.index("<!-- tools:end -->")]
    in_readme = sorted(re.findall(r"^\| `([a-z_]+)` \|", block, re.M))
    assert in_readme == names


def test_tool_names_are_snake_case_and_unique():
    tools = asyncio.run(server.list_tools())
    names = [t.name for t in tools]
    assert len(set(names)) == len(names)
    assert all(re.fullmatch(r"[a-z][a-z0-9_]*", n) for n in names)
