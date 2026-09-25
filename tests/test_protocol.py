"""Protocole Denon (telnet) : lecture des reponses et commandes envoyees.

Un faux ampli repond d'apres une table commande -> reponse et garde la liste
des commandes recues ; aucune connexion reseau.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from denon_mcp import server  # noqa: E402


class FakeDenon:
    def __init__(self, replies: dict[str, str]):
        self.replies = replies
        self.sent: list[str] = []

    def __call__(self, host: str, command: str) -> str:
        self.sent.append(command)
        reply = self.replies.get(command, "")
        if isinstance(reply, Exception):
            raise reply
        return reply


@pytest.fixture
def make(monkeypatch):
    monkeypatch.setattr(server.time, "sleep", lambda s: None)

    def _make(replies: dict[str, str]):
        ctl = server.DenonAVRController("192.0.2.10", 23)
        fake = FakeDenon(replies)
        monkeypatch.setattr(ctl, "_send_once", fake)
        return ctl, fake

    return _make


# ------------------------------------------------------------ volume
@pytest.mark.parametrize("reply,expected", [
    ("MV305", 30.5),          # demi-pas : 3 chiffres
    ("MV44", 44),
    ("MV05", 5),
    ("MVMAX 98\rMV44", 44),   # la ligne MVMAX (plafond) est ignoree
    ("MV445\rMVMAX 98", 44.5),
])
def test_get_volume_parse(make, reply, expected):
    ctl, _ = make({"MV?": reply})
    assert ctl.get_volume() == {"current": expected, "min": 0, "max": 98}


def test_get_volume_reponse_illisible(make):
    ctl, _ = make({"MV?": "PWSTANDBY"})
    assert "error" in ctl.get_volume()


def test_get_volume_injoignable(make):
    ctl, _ = make({"MV?": ConnectionRefusedError(111, "Connection refused")})
    assert ctl.get_volume()["error"].startswith("ERROR")


@pytest.mark.parametrize("level,command", [(44, "MV44"), (5, "MV05"), (150, "MV98"), (-3, "MV00")])
def test_volume_set_borne_et_formate(make, level, command):
    ctl, fake = make({"MV?": "MV44"})
    ctl.volume_set(level)
    assert fake.sent[0] == command


def test_volume_set_signale_un_ecart(make):
    ctl, _ = make({"MV?": "MV30"})
    assert ctl.volume_set(44) == "Volume partiellement regle (demande: 44, actuel: 30)"


def test_volume_up_repete_et_relit(make):
    ctl, fake = make({"MV?": "MV46"})
    assert ctl.volume_up(step=2) == "Volume: 46"
    assert fake.sent == ["MVUP", "MVUP", "MV?"]


# ------------------------------------------------------------ mute / power
def test_mute_toggle_lit_l_etat_reel(make):
    ctl, fake = make({"MU?": "MUON"})
    assert ctl.mute_toggle() == "Mute desactive"
    assert fake.sent == ["MU?", "MUOFF"]
    ctl, fake = make({"MU?": "MUOFF"})
    assert ctl.mute_toggle() == "Mute active"
    assert fake.sent == ["MU?", "MUON"]


def test_power_off_passe_en_standby(make):
    ctl, fake = make({})
    assert ctl.power_off() == "Denon en standby"
    assert fake.sent == ["PWSTANDBY"]


# ------------------------------------------------------------ statut
def test_get_status_allume(make):
    ctl, _ = make({"PW?": "PWON", "MV?": "MV305", "MU?": "MUOFF", "SI?": "SITV\rSVOFF"})
    assert ctl.get_status() == {"volume": 30.5, "power": "on", "muted": False, "source": "TV", "reachable": True}


def test_get_status_veille_joignable(make):
    ctl, _ = make({"PW?": "PWSTANDBY", "MV?": "", "MU?": "MUON", "SI?": "SIBD"})
    status = ctl.get_status()
    assert status["power"] == "standby" and status["reachable"] is True
    assert status["muted"] is True and status["source"] == "BD" and status["volume"] == -1


def test_get_status_injoignable(make):
    ctl, _ = make({"PW?": TimeoutError("timed out")})
    status = ctl.get_status()
    assert status["reachable"] is False and status["power"] == "unknown" and "error" in status


# ------------------------------------------------------------ sources
@pytest.mark.parametrize("asked,command", [("bluray", "SIBD"), ("TV", "SITV"), ("sat", "SISAT/CBL"), ("media", "SIMPLAY")])
def test_set_input_normalise(make, asked, command):
    ctl, fake = make({})
    ctl.set_input(asked)
    assert fake.sent == [command]


def test_set_input_inconnue_n_envoie_rien(make):
    ctl, fake = make({})
    assert ctl.set_input("vinyle").startswith("Source inconnue")
    assert fake.sent == []


# ------------------------------------------------------------ annotations MCP
def _hints(tool) -> dict:
    # noms du protocole (camelCase), quelle que soit la version du SDK
    return tool.annotations.model_dump(by_alias=True)


def test_chaque_outil_est_annote():
    for tool in server.list_tools():
        assert tool.annotations is not None, tool.name
        h = _hints(tool)
        assert h["destructiveHint"] is False, tool.name  # aucun outil n'ecrase de donnee
        assert h["readOnlyHint"] is tool.name.startswith("get_"), tool.name


def test_outils_cumulatifs_non_idempotents():
    by_name = {t.name: _hints(t) for t in server.list_tools()}
    for name in ("volume_up", "volume_down", "mute_toggle"):
        assert by_name[name]["idempotentHint"] is False, name
    for name in ("volume_set", "mute_on", "power_off", "set_input"):
        assert by_name[name]["idempotentHint"] is True, name


# ------------------------------------------------------------ ligne de commande
def test_cli_help_sans_configuration(monkeypatch, capsys):
    monkeypatch.delenv("DENON_HOST", raising=False)
    with pytest.raises(SystemExit) as exc:
        server.cli(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "DENON_HOST" in out and "DENON_MAC" in out


def test_cli_version(capsys):
    with pytest.raises(SystemExit) as exc:
        server.cli(["--version"])
    assert exc.value.code == 0
    assert "denon-mcp" in capsys.readouterr().out


def test_python_m_denon_mcp_version():
    import subprocess
    root = Path(__file__).resolve().parent.parent
    out = subprocess.run([sys.executable, "-m", "denon_mcp", "--version"], cwd=root,
                         capture_output=True, text=True, timeout=30)
    assert out.returncode == 0 and out.stdout.startswith("denon-mcp ")


# ------------------------------------------------------------ demarrage sans configuration
# Regression : sans DENON_HOST le serveur quittait au demarrage (sys.exit), donc un
# annuaire (Glama) qui le lance sans config pour lister ses outils voyait un echec.
_INTROSPECTION = "\n".join([
    '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18",'
    '"capabilities":{},"clientInfo":{"name":"t","version":"0"}}}',
    '{"jsonrpc":"2.0","method":"notifications/initialized"}',
    '{"jsonrpc":"2.0","id":2,"method":"tools/list"}',
    '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"get_status","arguments":{}}}',
]) + "\n"


def test_demarre_et_liste_les_outils_sans_configuration(tmp_path):
    import json
    import os
    import subprocess
    root = Path(__file__).resolve().parent.parent
    env = {"PATH": os.environ["PATH"], "HOME": str(tmp_path)}  # ni DENON_HOST ni config.yaml
    # stdin reste ouvert jusqu'a la reponse 3 : un client MCP ne ferme pas avant la fin
    proc = subprocess.Popen([sys.executable, "-m", "denon_mcp"], cwd=tmp_path, text=True,
                            env={**env, "PYTHONPATH": str(root)},
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    replies = {}
    try:
        proc.stdin.write(_INTROSPECTION)
        proc.stdin.flush()
        for line in proc.stdout:
            d = json.loads(line)
            if "id" in d:
                replies[d["id"]] = d
            if 3 in replies:
                break
    finally:
        proc.kill()
        proc.wait(timeout=10)
    assert len(replies[2]["result"]["tools"]) == len(server.list_tools())
    call = replies[3]["result"]
    assert "DENON_HOST" in call["content"][0]["text"]


def test_outil_sans_hote_repond_une_erreur_claire(make):
    ctl = server.DenonAVRController("", 23)
    assert "DENON_HOST" in ctl.get_volume()["error"]
