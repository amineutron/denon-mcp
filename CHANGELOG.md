# Changelog

Format : [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/), versions [SemVer](https://semver.org/lang/fr/).

## [0.3.1] - 2026-09-25

### Corrigé

- The server now starts without `DENON_HOST` (warning on stderr) instead of exiting: clients and directories (Glama) can list the tools without any configuration, and each tool call answers `ERROR: DENON_HOST not configured ...` until the receiver is set.

## [0.3.0] - 2026-09-25

### Modifié

- The code now lives in a `denon_mcp` package (`denon_mcp.server`). The wheel used to install a top-level `server` module, which overwrote the one of catt-mcp or pylips-mcp installed in the same environment (and vice versa). `python server.py` from a clone still works (thin launcher), and `python -m denon_mcp` is new.

## [0.2.2] - 2026-09-24

### Ajouté

- Follow the receiver by MAC address when DHCP changes its IP (`mac` in config.yaml or `DENON_MAC`)

### Corrigé

- `denon-mcp --help` and `--version` answer without any configuration (they used to start the server or fail on `DENON_HOST`)

## [0.2.1] - 2026-09-24

### Ajouté

- **registry** : MCP registry manifest and package ownership marker

## [0.2.0] - 2026-09-24

### Ajouté
- `get_status` renvoie aussi `muted`, `source` et `reachable` : un ampli en veille (répond `PWSTANDBY`) est distingué d'un ampli injoignable.
- Annotations MCP (`readOnlyHint`, `idempotentHint`, `destructiveHint`) sur chaque outil.
- Workflow de release sur tag `v*` : build du wheel, publication PyPI par Trusted Publishing, release GitHub.
- Démo enregistrée (GIF) et script de régénération.

### Modifié
- Migration vers `mcp` 2.

### Corrigé
- `mute_toggle` lit l'état de l'ampli avant de basculer (le Denon n'a pas de commande toggle) et ne bloque plus la boucle d'événements.

## [0.1.0] - 2026-09-09

Première version publiée : configuration autonome, wheel installable avec point d'entrée, table des outils générée, tests et CI.
