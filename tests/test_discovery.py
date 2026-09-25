"""Redecouverte de l'IP du Denon par son adresse MAC (DHCP sans reservation)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from denon_mcp import server  # noqa: E402

NEIGH = """192.0.2.22 dev eth0 lladdr 00:11:22:33:44:55 REACHABLE
192.0.2.26 dev eth0 lladdr 00:06:78:12:34:56 STALE
192.0.2.40 dev eth0 FAILED
fe80::1 dev eth0 lladdr 00:06:78:12:34:56 router STALE
"""


@pytest.mark.parametrize("mac", ["00:06:78:12:34:56", "000678123456", "00-06-78-12-34-56"])
def test_ip_for_mac_formats(mac):
    assert server.ip_for_mac(NEIGH, mac) == "192.0.2.26"


def test_ip_for_mac_absente():
    assert server.ip_for_mac(NEIGH, "11:22:33:44:55:66") is None


def test_ip_for_mac_ignore_ipv6_et_entrees_sans_mac():
    assert server.ip_for_mac("192.0.2.40 dev eth0 FAILED\nfe80::1 dev x lladdr 00:06:78:12:34:56 STALE\n",
                             "000678123456") is None


def test_normalize_mac_invalide():
    assert server.normalize_mac("pas une mac") == ""


def test_subnet_hosts_24():
    hosts = server.subnet_hosts("192.0.2.22")
    assert len(hosts) == 254 and hosts[0] == "192.0.2.1" and hosts[-1] == "192.0.2.254"


def test_send_command_rebascule_sur_la_nouvelle_ip(monkeypatch):
    ctl = server.DenonAVRController("192.0.2.22", 23, mac="000678123456")
    calls = []

    def fake_once(host, command):
        calls.append(host)
        if host == "192.0.2.22":
            raise ConnectionRefusedError(111, "Connection refused")
        return "MV305"

    monkeypatch.setattr(ctl, "_send_once", fake_once)
    monkeypatch.setattr(server, "rediscover_host", lambda mac, hint: "192.0.2.26")
    assert ctl._send_command("MV?") == "MV305"
    assert ctl.host == "192.0.2.26" and calls == ["192.0.2.22", "192.0.2.26"]


def test_send_command_sans_mac_pas_de_redecouverte(monkeypatch):
    ctl = server.DenonAVRController("192.0.2.22", 23)
    monkeypatch.setattr(ctl, "_send_once", lambda h, c: (_ for _ in ()).throw(ConnectionRefusedError(111, "refused")))
    monkeypatch.setattr(server, "rediscover_host", lambda mac, hint: pytest.fail("ne doit pas etre appele"))
    assert ctl._send_command("MV?").startswith("ERROR")


def test_rediscover_limite_dans_le_temps(monkeypatch):
    monkeypatch.setattr(server, "_last_discovery", 0.0)
    monkeypatch.setattr(server, "_read_neigh", lambda: NEIGH)
    monkeypatch.setattr(server, "_warm_arp", lambda hosts: None)
    monkeypatch.setattr(server.time, "monotonic", lambda: 1000.0)
    assert server.rediscover_host("000678123456", "192.0.2.22") == "192.0.2.26"
    # deuxieme appel dans la fenetre : pas de nouvelle recherche
    assert server.rediscover_host("000678123456", "192.0.2.22") is None
