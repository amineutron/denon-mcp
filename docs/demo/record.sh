#!/usr/bin/env bash
# Regenere docs/assets/demo.gif : un client MCP minimal (mcp_demo.py) demarre le serveur en stdio,
# liste les outils puis appelle des outils en lecture seule. Les adresses IP privees et MAC sont masquees.
# Prerequis : asciinema (pip/uv tool), agg (https://github.com/asciinema/agg), uv, et la configuration
# du serveur dans l'environnement (voir README). Aucune valeur secrete n'est affichee.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
cd "$ROOT"
export DEMO_SHOW='uv run python server.py   # depot denon-mcp, DENON_HOST dans l'environnement'
asciinema rec --overwrite --cols 100 --rows 30 --idle-time-limit 2 \
  --command "uv run python $HERE/mcp_demo.py 'uv run python server.py' get_status" /tmp/demo.cast
agg --font-size 15 --cols 100 --rows 30 --theme monokai /tmp/demo.cast "$ROOT/docs/assets/demo.gif"
ls -la "$ROOT/docs/assets/demo.gif"
