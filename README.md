# Denon MCP Server

[![tests](https://github.com/amineutron/denon-mcp/actions/workflows/tests.yml/badge.svg)](https://github.com/amineutron/denon-mcp/actions/workflows/tests.yml) [![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE) [![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)

**English summary.** MCP server for Denon AVR home-cinema receivers over the local telnet control protocol: power, volume, mute, inputs, status. Configure with `DENON_HOST` / `DENON_PORT` or a `config.yaml`; runs standalone (`uvx denon-mcp` after PyPI publication).

Serveur MCP pour contrôler un Home Cinema Denon AVR via le protocole Denon AVR Control (telnet).

## Modèle supporté

- **Denon AVR-X1700H DAB**
- Autres modèles AVR-X series compatibles avec le protocole Denon AVR Control

## Configuration

Ordre de résolution : variables d'environnement, puis fichier YAML (DENON_CONFIG, sinon `./config.yaml`, sinon `config.yaml` à côté du serveur, sinon celui de Lyra si le serveur est installé dans son arborescence). Le serveur fonctionne seul, sans Lyra.

## Installation en une ligne

```bash
uvx denon-mcp          # après publication sur PyPI ; en attendant : uvx --from git+https://github.com/amineutron/denon-mcp denon-mcp
```


Ajouter dans `config.yaml` :

```yaml
denon:
  host: "192.0.2.10"        # IP du Denon (exemple)
  port: 23                   # Port telnet (default: 23)
```

Les valeurs ci-dessous sont des exemples : remplacez-les par les valeurs de votre appareil
(IP affichée dans le menu réseau de l'ampli, adresse MAC au format `AA:BB:CC:DD:EE:FF`
utile pour une réservation DHCP ou le Wake-on-LAN).

## Outils disponibles

<!-- tools:start -->
| Outil | Rôle |
|---|---|
| `volume_set` | Regle le volume du Denon a un niveau specifique (0-98). 80 = 0dB reference. |
| `volume_up` | Augmente le volume du Denon. |
| `volume_down` | Baisse le volume du Denon. |
| `mute_on` | Active le mute du Denon. |
| `mute_off` | Desactive le mute du Denon. |
| `mute_toggle` | Toggle le mute du Denon (on/off). |
| `power_on` | Allume le Denon AVR. |
| `power_off` | Eteint le Denon AVR (standby). |
| `get_status` | Retourne le statut du Denon (volume, power, etc.). |
| `set_input` | Change la source d'entree du Denon (BD, TV, GAME, SAT/CBL, DVD, MPLAY). |
<!-- tools:end -->

## Sources d'entrée

- `BD` : Blu-ray / Lecteur BD
- `TV` : Entrée TV
- `GAME` : Console de jeu
- `SAT/CBL` : Satellite / Câble
- `DVD` : Lecteur DVD
- `MPLAY` : Media Player

Aliases supportés : `bluray`, `blu-ray`, `cable`, `sat`, `media`, `mediaplayer`

## Échelle de volume

- **0-98** : Échelle Denon (0 = -80 dB, 80 = 0 dB référence, 98 = +18 dB)
- Pour une écoute normale : **30-50**
- Pour un home cinéma : **50-70**
- Maximum recommandé : **80** (0 dB)

## Protocole Denon AVR Control

Commandes telnet sur port 23 :
- `MV44` : Volume 44
- `MV?` : Demander le volume actuel
- `MVUP` / `MVDOWN` : Volume +/-
- `PWON` / `PWSTANDBY` : Power on/off
- `MUON` / `MUOFF` : Mute on/off
- `SIBD` : Source Blu-ray

## Notes HDMI ARC

Quand un home cinéma est connecté en **HDMI ARC/eARC** à la TV :
- Le volume de la TV est désactivé
- C'est le home cinéma qui contrôle le volume audio
- Les commandes `tv.volume_*` ne fonctionnent PAS
- Utiliser `denon.volume_*` à la place

## Test manuel

```bash
# Test connexion
echo "MV?" | nc 192.0.2.10 23

# Régler volume à 44
echo "MV44" | nc 192.0.2.10 23

# Allumer
echo "PWON" | nc 192.0.2.10 23
```

## Installation

```bash
cd mcp-servers/denon-mcp
python server.py
```

Le serveur est automatiquement lancé par Lyra via la config MCP.

## Part of the Lyra ecosystem

| Dépôt | Rôle |
|---|---|
| [lyra](https://github.com/amineutron/lyra) | assistant DevOps vocal, local par défaut (AGPL-3.0) |
| [fedora-agents](https://github.com/amineutron/fedora-agents) | MCP : machines virtuelles KVM et sauvegardes |
| [mcp-tracking](https://github.com/amineutron/mcp-tracking) | MCP + API + tableau de bord des tâches longues |
| [neutroncore](https://github.com/amineutron/neutroncore) | hub PWA du homelab |
| [hue-mcp](https://github.com/amineutron/hue-mcp) | MCP Philips Hue (fork de ThomasRohde/hue-mcp) |
| [pylips-mcp](https://github.com/amineutron/pylips-mcp) | MCP TV Philips |
| [denon-mcp](https://github.com/amineutron/denon-mcp) | MCP ampli Denon |
| [catt-mcp](https://github.com/amineutron/catt-mcp) | MCP Chromecast et DLNA |
