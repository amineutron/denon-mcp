# Denon MCP Server

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE) [![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)

Serveur MCP pour contrôler un Home Cinema Denon AVR via le protocole Denon AVR Control (telnet).

## Modèle supporté

- **Denon AVR-X1700H DAB**
- Autres modèles AVR-X series compatibles avec le protocole Denon AVR Control

## Configuration

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

| Outil | Description | Arguments |
|-------|-------------|-----------|
| `volume_set` | Règle le volume (0-98, 80 = 0dB référence) | `level` (int) |
| `volume_up` | Augmente le volume | `step` (int, default: 1) |
| `volume_down` | Baisse le volume | `step` (int, default: 1) |
| `mute_on` | Active le mute | - |
| `mute_off` | Désactive le mute | - |
| `mute_toggle` | Toggle le mute | - |
| `power_on` | Allume le Denon | - |
| `power_off` | Éteint le Denon (standby) | - |
| `get_status` | Statut (volume, power) | - |
| `set_input` | Change la source (BD, TV, GAME, etc.) | `source` (string) |

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
