# Changelog

Format : [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/), versions [SemVer](https://semver.org/lang/fr/).

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
