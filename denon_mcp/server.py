#!/usr/bin/env python3
"""
MCP Server pour Denon AVR - Controle Home Cinema Denon.

Ce serveur expose les commandes Denon AVR via le protocole MCP pour
permettre a Lyra de controler le home cinema avec une latence minimale.

Protocole: Denon AVR Control Protocol via telnet (port 23)
Modele supporte: AVR-X1700H DAB (et autres AVR-X series)

Usage:
    python server.py

Configuration:
    Les parametres Denon sont lus depuis config.yaml ou variables d'env:
    - DENON_HOST: IP du Denon
    - DENON_PORT: Port telnet (default: 23)
    - DENON_MAC: adresse MAC (optionnel) : si l'IP ne repond plus (bail DHCP
      change, pas de reservation possible), le serveur retrouve la nouvelle
      IP par la table de voisinage du reseau local et bascule dessus.
"""

import asyncio
import ipaddress
import json
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

try:
    from mcp.server import Server, ServerRequestContext
    from mcp.server.stdio import stdio_server
    from mcp.types import (
        CallToolRequestParams,
        CallToolResult,
        ListToolsResult,
        PaginatedRequestParams,
        TextContent,
        Tool,
        ToolAnnotations,
    )
except ImportError:
    print("Error: mcp package not installed. Run: pip install mcp", file=sys.stderr)
    sys.exit(1)


# Racine du depot (le code vit dans denon_mcp/) : config.yaml a cote du serveur
# ou celui de Lyra quand le depot est dans son arborescence (lyra/mcp-servers/).
_REPO_ROOT = Path(__file__).resolve().parent.parent


def load_config() -> dict:
    """Charge la configuration Denon depuis config.yaml ou variables d'env."""
    # Ordre de resolution : variables d'environnement, puis fichier YAML
    # (DENON_CONFIG, sinon ./config.yaml, sinon le config.yaml de Lyra si le
    # serveur est installe dans son arborescence).
    config = {
        "host": os.environ.get("DENON_HOST", ""),
        "port": int(os.environ.get("DENON_PORT", "23")),
        "mac": os.environ.get("DENON_MAC", ""),
    }
    candidates = [Path(p) for p in (os.environ.get("DENON_CONFIG", ""),) if p]
    candidates += [Path.cwd() / "config.yaml", _REPO_ROOT / "config.yaml",
                   _REPO_ROOT.parent.parent / "config.yaml"]
    for config_path in candidates:
        if not config_path.exists():
            continue
        try:
            import yaml
            with open(config_path) as f:
                cfg = yaml.safe_load(f) or {}
            denon_cfg = cfg.get("denon", {}) or {}
            if not config["host"]:
                config["host"] = denon_cfg.get("host", "") or ""
                config["port"] = int(denon_cfg.get("port", config["port"]))
            if not config["mac"]:
                config["mac"] = str(denon_cfg.get("mac", "") or "")
        except Exception as e:  # fichier illisible : on continue avec l'env
            print(f"Warning: Could not load {config_path}: {e}", file=sys.stderr)
        break
    return config


# --------------------------------------------------------------------------- #
# Redecouverte par adresse MAC
# --------------------------------------------------------------------------- #
DISCOVERY_COOLDOWN_S = 120
_last_discovery = 0.0


def normalize_mac(mac: str) -> str:
    """'00:06:78:12:34:56', '000678123456', '00-06-...' -> '000678123456' ('' si invalide)."""
    hexa = re.sub(r"[^0-9a-fA-F]", "", mac or "").lower()
    return hexa if len(hexa) == 12 else ""


def ip_for_mac(neigh_text: str, mac: str) -> str | None:
    """IPv4 associee a `mac` dans la sortie de `ip neigh` (None si absente)."""
    target = normalize_mac(mac)
    if not target:
        return None
    for line in neigh_text.splitlines():
        parts = line.split()
        if "lladdr" not in parts or not parts:
            continue
        lladdr = parts[parts.index("lladdr") + 1] if parts.index("lladdr") + 1 < len(parts) else ""
        try:
            is_v4 = ipaddress.ip_address(parts[0]).version == 4
        except ValueError:
            continue
        if is_v4 and normalize_mac(lladdr) == target:
            return parts[0]
    return None


def subnet_hosts(hint_ip: str) -> list[str]:
    """Hotes du /24 de l'ancienne IP (le Denon reste sur le meme reseau local)."""
    net = ipaddress.ip_network(f"{hint_ip}/24", strict=False)
    return [str(h) for h in net.hosts()]


def _read_neigh() -> str:
    try:
        return subprocess.run(["ip", "neigh"], capture_output=True, text=True, timeout=3).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def _warm_arp(hosts: list[str]) -> None:
    """Un datagramme UDP par hote force le noyau a resoudre sa MAC (pas de
    sous-processus, pas de droits particuliers) ; on laisse 1,5 s aux reponses."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        for host in hosts:
            try:
                sock.sendto(b"", (host, 9))  # port discard
            except OSError:
                continue
    time.sleep(1.5)


def rediscover_host(mac: str, hint_ip: str) -> str | None:
    """Nouvelle IP du Denon d'apres sa MAC, au plus une recherche par cooldown."""
    global _last_discovery
    now = time.monotonic()
    if now - _last_discovery < DISCOVERY_COOLDOWN_S:
        return None
    _last_discovery = now
    found = ip_for_mac(_read_neigh(), mac)
    if found is None:
        try:
            _warm_arp(subnet_hosts(hint_ip))
        except ValueError:
            return None
        found = ip_for_mac(_read_neigh(), mac)
    return found


# Attente maximale de la reponse a une commande. Mesure sur un AVR-X1700H :
# 15 a 60 ms ; au-dela, on passe a la suite (ampli en veille qui ne repond pas
# a tout, commande d'allumage lente).
REPLY_TIMEOUT_S = 0.8
# Un ordre (MV44, MVUP, MUON...) n'est pas toujours acquitte : regler le volume a sa
# valeur actuelle ne renvoie rien. On attend au plus cet ecart (le protocole Denon
# demande ~50 ms entre deux commandes), la relecture qui suit donne l'etat reel.
COMMAND_GAP_S = 0.15


def reply_prefix(command: str) -> str:
    """Prefixe des reponses du Denon a une commande : 2 lettres (PW, MV, MU, SI...)."""
    return command[:2]


def is_reply(line: str, prefix: str) -> bool:
    """La ligne repond-elle a une commande de ce prefixe ? MVMAX (plafond de volume)
    commence par MV mais n'est pas une reponse de volume."""
    return line.startswith(prefix) and not (prefix == "MV" and line.startswith("MVMAX"))


_NO_HOST = "DENON_HOST not configured (env DENON_HOST, or denon.host in config.yaml)"


class DenonAVRController:
    """Controleur pour Home Cinema Denon via telnet."""

    def __init__(self, host: str, port: int = 23, mac: str = ""):
        self.host = host
        self.port = port
        self.mac = mac
        self.timeout = 3

    def _send_command(self, command: str) -> str:
        """Envoie une commande au Denon et retourne la reponse brute."""
        return self._send_commands([command])

    def _send_commands(self, commands: list[str]) -> str:
        """Envoie des commandes dans UNE connexion telnet et retourne toutes les lignes
        recues (separees par \\r). Avant : une connexion et 0,3 s d'attente par commande."""
        if not self.host:
            return f"ERROR: {_NO_HOST}"
        try:
            return self._send_once(self.host, commands)
        except OSError as first:
            # IP changee par le DHCP ? on retrouve le Denon par sa MAC et on reessaie une fois
            new_host = rediscover_host(self.mac, self.host) if self.mac else None
            if new_host and new_host != self.host:
                print(f"Denon: {self.host} injoignable, nouvelle IP {new_host} (MAC {self.mac})", file=sys.stderr)
                self.host = new_host
                try:
                    return self._send_once(self.host, commands)
                except OSError as second:
                    return self._error(second)
            return self._error(first)
        except Exception as e:  # reponse illisible, commande non ASCII... : jamais d'exception vers MCP
            return f"ERROR: {e}"

    @staticmethod
    def _error(exc: OSError) -> str:
        if isinstance(exc, socket.timeout):
            return "ERROR: Timeout - Denon may be off"
        return f"ERROR: {exc}"

    def _send_once(self, host: str, commands: list[str]) -> str:
        """Une connexion telnet : chaque commande est envoyee puis sa reponse attendue
        (ligne au bon prefixe, au plus REPLY_TIMEOUT_S) avant la suivante. Les lignes sont
        rendues dans l'ordre d'arrivee ; le Denon en envoie parfois en retard (MVMAX),
        d'ou l'attribution par prefixe dans les lecteurs. Leve OSError."""
        lines: list[str] = []
        pending = ""
        with socket.create_connection((host, self.port), timeout=self.timeout) as sock:
            for command in commands:
                prefix = reply_prefix(command)
                sock.send(f"{command}\r".encode('ascii'))
                wait = REPLY_TIMEOUT_S if command.endswith("?") else COMMAND_GAP_S
                deadline = time.monotonic() + wait
                answered = False
                while not answered:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    sock.settimeout(remaining)
                    try:
                        chunk = sock.recv(1024)
                    except socket.timeout:
                        break
                    if not chunk:
                        break
                    pending += chunk.decode('ascii', errors='ignore')
                    *complete, pending = pending.split('\r')
                    for line in (x.strip() for x in complete):
                        if line:
                            lines.append(line)
                            answered = answered or is_reply(line, prefix)
        if pending.strip():
            lines.append(pending.strip())
        return "\r".join(lines)

    @staticmethod
    def _parse_volume(response: str) -> dict:
        """Derniere valeur de volume de la reponse : MV245 -> 24.5, MV44 -> 44 (MVMAX ignore)."""
        if "ERROR" in response:
            return {"error": response}
        values = [line[2:] for line in response.split('\r') if is_reply(line, "MV")]
        if not values:
            return {"error": "Could not parse volume"}
        vol_str = values[-1]
        if len(vol_str) == 3 and vol_str.isdigit():
            volume = float(vol_str) / 10
        elif vol_str.isdigit():
            volume = int(vol_str)
        else:
            volume = -1
        return {"current": volume, "min": 0, "max": 98}

    def get_volume(self) -> dict:
        """Retourne le volume actuel."""
        return self._parse_volume(self._send_command("MV?"))

    def volume_set(self, level: int) -> str:
        """Regle le volume (0-98, 80 = 0 dB) et le relit dans la meme session."""
        level = max(0, min(98, level))
        # Format Denon : MV44 pour 44 (entiers seulement)
        response = self._send_commands([f"MV{level:02d}", "MV?"])
        if "ERROR" in response:
            return f"Erreur: {response}"
        check = self._parse_volume(response)
        if "error" not in check:
            actual = check["current"]
            if abs(actual - level) < 0.6:  # Tolerance 0.5
                return f"Volume regle a {level}"
            return f"Volume partiellement regle (demande: {level}, actuel: {actual})"
        return f"Volume regle a {level}"

    def _volume_step(self, command: str, step: int, fallback: str) -> str:
        response = self._send_commands([command] * max(1, step) + ["MV?"])
        if "ERROR" in response:
            return f"Erreur: {response}"
        vol = self._parse_volume(response)
        return f"Volume: {vol['current']}" if "error" not in vol else fallback

    def volume_up(self, step: int = 1) -> str:
        """Augmente le volume de `step` pas (une session, relecture a la fin)."""
        return self._volume_step("MVUP", step, "Volume augmente")

    def volume_down(self, step: int = 1) -> str:
        """Baisse le volume de `step` pas (une session, relecture a la fin)."""
        return self._volume_step("MVDOWN", step, "Volume baisse")

    def mute_on(self) -> str:
        """Active le mute."""
        response = self._send_command("MUON")
        if "ERROR" not in response:
            return "Mute active"
        return f"Erreur: {response}"

    def mute_off(self) -> str:
        """Desactive le mute."""
        response = self._send_command("MUOFF")
        if "ERROR" not in response:
            return "Mute desactive"
        return f"Erreur: {response}"

    def mute_toggle(self) -> str:
        """Bascule le mute en interrogeant d'abord l'etat reel.

        Le Denon n'a pas de commande toggle. L'ancien code envoyait MUON a
        l'aveugle : demander "coupe le son" deux fois laissait le son coupe.
        """
        etat = self._send_command("MU?")
        if "ERROR" in etat:
            return f"Erreur: {etat}"

        muet = any(ligne.strip() == "MUON" for ligne in etat.split('\r'))
        response = self._send_command("MUOFF" if muet else "MUON")
        if "ERROR" in response:
            return f"Erreur: {response}"
        return "Mute desactive" if muet else "Mute active"

    def power_on(self) -> str:
        """Allume le Denon."""
        response = self._send_command("PWON")
        if "ERROR" not in response:
            return "Denon allume"
        return f"Erreur: {response}"

    def power_off(self) -> str:
        """Eteint le Denon (standby)."""
        response = self._send_command("PWSTANDBY")
        if "ERROR" not in response:
            return "Denon en standby"
        return f"Erreur: {response}"

    def get_status(self) -> dict:
        """Statut complet (alimentation, volume, sourdine, source) en une seule session."""
        response = self._send_commands(["PW?", "MV?", "MU?", "SI?"])
        lines = [line.strip() for line in response.split('\r')]
        if "ERROR" in response or not any(is_reply(line, "PW") for line in lines):
            # Injoignable (eteint au secteur, reseau) : distinct de la veille,
            # qui repond PWSTANDBY.
            return {"volume": None, "power": "unknown", "muted": False,
                    "source": None, "reachable": False, "error": response or "ERROR: no reply"}
        sources = [line for line in lines if is_reply(line, "SI")]
        return {
            "volume": self._parse_volume(response).get("current", -1),
            "power": "on" if "PWON" in lines else "standby",
            "muted": "MUON" in lines,
            "source": sources[0][2:] if sources else None,
            "reachable": True,
        }

    def set_input(self, source: str) -> str:
        """Change la source d'entree.

        Args:
            source: Source (ex: "BD", "TV", "GAME", "SAT/CBL", "DVD", "MPLAY")

        Returns:
            Message de confirmation
        """
        # Normaliser la source
        source_map = {
            "bluray": "BD",
            "blu-ray": "BD",
            "bd": "BD",
            "tv": "TV",
            "game": "GAME",
            "sat": "SAT/CBL",
            "cable": "SAT/CBL",
            "dvd": "DVD",
            "media": "MPLAY",
            "mediaplayer": "MPLAY",
        }

        source_cmd = source_map.get(source.lower())
        if source_cmd is None:
            valid = ", ".join(sorted(source_map.keys()))
            return f"Source inconnue: {source!r}. Sources valides: {valid}"

        response = self._send_command(f"SI{source_cmd}")
        if "ERROR" not in response:
            return f"Source changee: {source_cmd}"
        return f"Erreur: {response}"


# Initialiser le serveur MCP
config: dict = {}
denon = None  # instancie dans main() : l'import du module ne doit rien exiger


# Profils d'annotations MCP (ToolAnnotations) : ils disent au client ce que fait
# un outil avant de l'appeler. Aucun outil de ce serveur n'ecrase de donnee,
# donc destructiveHint reste False ; la distinction utile est la lecture seule
# et l'idempotence (rejouable sans effet cumulatif).
_READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)
_SET = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True)
_ACTION = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True)


def list_tools() -> list[Tool]:
    """Liste les outils disponibles."""
    return [
        Tool(
            name="volume_set",
            annotations=_SET,
            description="Regle le volume du Denon a un niveau specifique (0-98). 80 = 0dB reference.",
            inputSchema={
                "type": "object",
                "properties": {
                    "level": {
                        "type": "integer",
                        "description": "Niveau de volume (0-98)",
                        "minimum": 0,
                        "maximum": 98,
                    }
                },
                "required": ["level"],
            },
        ),
        Tool(
            name="volume_up",
            annotations=_ACTION,
            description="Augmente le volume du Denon.",
            inputSchema={
                "type": "object",
                "properties": {
                    "step": {
                        "type": "integer",
                        "description": "Nombre de fois a augmenter (default: 1)",
                        "minimum": 1,
                        "maximum": 10,
                        "default": 1,
                    }
                },
            },
        ),
        Tool(
            name="volume_down",
            annotations=_ACTION,
            description="Baisse le volume du Denon.",
            inputSchema={
                "type": "object",
                "properties": {
                    "step": {
                        "type": "integer",
                        "description": "Nombre de fois a baisser (default: 1)",
                        "minimum": 1,
                        "maximum": 10,
                        "default": 1,
                    }
                },
            },
        ),
        Tool(
            name="mute_on",
            annotations=_SET,
            description="Active le mute du Denon.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="mute_off",
            annotations=_SET,
            description="Desactive le mute du Denon.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="mute_toggle",
            annotations=_ACTION,
            description="Toggle le mute du Denon (on/off).",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="power_on",
            annotations=_SET,
            description="Allume le Denon AVR.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="power_off",
            annotations=_SET,
            description="Eteint le Denon AVR (standby).",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="get_status",
            annotations=_READ,
            description="Retourne le statut du Denon : volume, power (on/standby/unknown), muted, source (BD, TV, GAME...), reachable.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="set_input",
            annotations=_SET,
            description="Change la source d'entree du Denon (BD, TV, GAME, SAT/CBL, DVD, MPLAY).",
            inputSchema={
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "description": "Source (ex: BD, TV, GAME, SAT/CBL, DVD, MPLAY)",
                    }
                },
                "required": ["source"],
            },
        ),
    ]


def _dispatch(name: str, arguments: Any) -> str:
    """Aiguillage synchrone vers le controleur (sockets et temporisations)."""
    if name == "volume_set":
        level = arguments.get("level")
        result = denon.volume_set(level)
    elif name == "volume_up":
        step = arguments.get("step", 1)
        result = denon.volume_up(step)
    elif name == "volume_down":
        step = arguments.get("step", 1)
        result = denon.volume_down(step)
    elif name == "mute_on":
        result = denon.mute_on()
    elif name == "mute_off":
        result = denon.mute_off()
    elif name == "mute_toggle":
        result = denon.mute_toggle()
    elif name == "power_on":
        result = denon.power_on()
    elif name == "power_off":
        result = denon.power_off()
    elif name == "get_status":
        result = json.dumps(denon.get_status(), indent=2)
    elif name == "set_input":
        source = arguments.get("source")
        result = denon.set_input(source)
    else:
        result = f"Unknown tool: {name}"

    return result


async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Execute un outil.

    Le controleur parle en telnet avec des temporisations : l'appeler
    directement figerait la boucle asyncio du serveur (et donc tout autre
    appel en cours). On le deporte dans un thread.
    """
    try:
        result = await asyncio.to_thread(_dispatch, name, arguments)
        return [TextContent(type="text", text=result)]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]


async def handle_list_tools(ctx: ServerRequestContext, params: PaginatedRequestParams | None) -> ListToolsResult:
    return ListToolsResult(tools=list_tools())


async def handle_call_tool(ctx: ServerRequestContext, params: CallToolRequestParams) -> CallToolResult:
    return CallToolResult(content=await call_tool(params.name, params.arguments or {}))


app = Server("denon-mcp", on_list_tools=handle_list_tools, on_call_tool=handle_call_tool)


def _connect() -> None:
    """Charge la configuration et instancie le controleur (au demarrage, pas a l'import)."""
    global config, denon
    config = load_config()
    if not config["host"]:
        # On demarre quand meme : un client (ou un annuaire comme Glama) doit pouvoir
        # lister les outils sans configuration ; chaque appel dira ce qui manque.
        print(f"Warning: {_NO_HOST}", file=sys.stderr)
    denon = DenonAVRController(config["host"], config["port"], config.get("mac", ""))


async def main():
    """Point d'entree principal."""
    _connect()
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())


def cli(argv: list[str] | None = None) -> None:
    """Point d'entree console (pip/uvx) : lance le serveur MCP sur stdio.
    --help et --version repondent sans configuration ni ampli."""
    import argparse

    from denon_mcp import __version__ as ver
    parser = argparse.ArgumentParser(
        prog="denon-mcp",
        description="MCP server for Denon AVR receivers (telnet control protocol, stdio transport).",
        epilog="Configuration: DENON_HOST (required), DENON_PORT (default 23), DENON_MAC (optional, follow the "
               "receiver when DHCP changes its IP), DENON_CONFIG (path to a config.yaml with a `denon:` section).",
    )
    parser.add_argument("--version", action="version", version=f"denon-mcp {ver}")
    parser.parse_args(argv)
    asyncio.run(main())
