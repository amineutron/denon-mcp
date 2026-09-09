#!/usr/bin/env python3
"""Regenere le tableau des outils du README depuis list_tools() du serveur.

Usage : uv run python scripts/gen_tools_table.py [--check]
Le tableau est place entre les marqueurs <!-- tools:start --> et <!-- tools:end -->.
"""
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("MCP_TOOLS_TABLE", "1")  # les serveurs ne doivent rien charger de bloquant a l'import


def rows():
    import server  # noqa: E402
    tools = asyncio.run(server.list_tools())
    return [(t.name, (t.description or "").strip().split("\n")[0]) for t in tools]


def table():
    lines = ["| Outil | Rôle |", "|---|---|"]
    lines += [f"| `{n}` | {d} |" for n, d in rows()]
    return "\n".join(lines)


START, END = "<!-- tools:start -->", "<!-- tools:end -->"


def main() -> int:
    readme = ROOT / "README.md"
    doc = readme.read_text(encoding="utf-8")
    if START not in doc or END not in doc:
        print(f"marqueurs {START} / {END} absents du README", file=sys.stderr)
        return 2
    new = doc[: doc.index(START) + len(START)] + "\n" + table() + "\n" + doc[doc.index(END):]
    if "--check" in sys.argv:
        if new != doc:
            print("README périmé : lancez scripts/gen_tools_table.py", file=sys.stderr)
            return 1
        print(f"README à jour ({len(rows())} outils)")
        return 0
    readme.write_text(new, encoding="utf-8")
    print(f"README régénéré ({len(rows())} outils)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
