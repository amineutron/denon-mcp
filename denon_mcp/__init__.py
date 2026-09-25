"""denon-mcp : serveur MCP pour amplis Denon AVR (protocole telnet)."""
from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("denon-mcp")
except PackageNotFoundError:  # lance depuis le depot sans installation
    __version__ = "dev"
