#!/usr/bin/env python3
"""Lanceur depuis le depot (Lyra, `python server.py`) : le code est dans denon_mcp/.

Ce fichier n'est pas dans le wheel : installe, le serveur se lance avec la
commande `denon-mcp` (ou `uvx denon-mcp`, `python -m denon_mcp`).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from denon_mcp.server import cli  # noqa: E402

if __name__ == "__main__":
    cli()
