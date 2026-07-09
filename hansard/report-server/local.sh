#!/usr/bin/env bash
# Local deployment of the hansard report worker — the SAME code Cloudflare runs, on this box.
#
#   ./local.sh [port]        (default 8787)
#
# wrangler dev --local runs the worker in miniflare: local R2 + Durable Objects persisted under
# data_root/worker-local, secrets read from .dev.vars (auto-generated on first run, gitignored).
# Binds 0.0.0.0 so LAN devices can browse http://<this-box>:<port>. Auth model for local use:
# the machine's raw token (data_root/.token) — open http://<box>:<port>/?token=<raw token> once,
# the magic-link cookie does the rest. Google login needs a localhost redirect URI in the Google
# console and the GOOGLE_* lines in .dev.vars; it is OPTIONAL for local use.
#
# NOTE: run this from a NON-git copy (the plugin cache) or this repo checkout — wrangler 4.86
# resolves paths against the git root INSIDE a repo whose plugin lives in a subdir (the doubled
# trainlint/trainlint scar); the plugin cache copy has no .git, so keepalive uses that one.
set -e
export PATH="$HOME/.local/bin:$HOME/.local/node/bin:$PATH"
cd "$(dirname "$0")/worker"

PORT="${1:-${HANSARD_LOCAL_PORT:-8787}}"
DR="${HANSARD_DATA_DIR:-${TRAINLINT_DATA_DIR:-$HOME/.claude/plugins/data/hansard-hansard}}"

if [ ! -f .dev.vars ]; then
  echo "[local.sh] creating .dev.vars (local-only secrets — gitignored)"
  {
    printf 'TOKEN_SIGNING_KEY=%s\n' "$(openssl rand -hex 32)"
    printf 'ADMIN_EMAILS=%s\n' "${HANSARD_LOCAL_ADMIN:-voidrank@gmail.com}"
    # GOOGLE_CLIENT_ID=...     # optional: add a http://localhost:<port>/auth/google/callback
    # GOOGLE_CLIENT_SECRET=... # redirect URI in the Google console to enable Google login locally
  } > .dev.vars
fi

mkdir -p "$DR/worker-local"
exec wrangler dev --local --ip 0.0.0.0 --port "$PORT" --persist-to "$DR/worker-local"
