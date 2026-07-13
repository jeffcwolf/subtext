#!/usr/bin/env bash
#
# deploy.sh — build Subtext for the amd64 server, push to the Scaleway registry,
# and roll just this service in the shared Caddy stack.
#
# Pattern A (containerized server app): Subtext is a Leptos SSR + Axum binary
# that listens on a port; the shared Caddy container reverse-proxies to it. This
# script builds + pushes the image and rolls the `subtext` service. It NEVER
# touches Caddy or the compose file — the routing block lives in scaleway-infra.
#
# Overridable via env (defaults target the discrepancies.eu box):
#   DEPLOY_SSH        wolf@51.158.67.158        SSH target (key auth, no sudo)
#   DEPLOY_REGISTRY   rg.fr-par.scw.cloud       Scaleway Container Registry
#   DEPLOY_NAMESPACE  discrepancies             registry namespace
#   DEPLOY_IMAGE      $REGISTRY/$NAMESPACE/subtext   full image (overrides the two above)
#   DEPLOY_TAG        latest                    the moving tag (also always tags :<git-sha>)
#   DEPLOY_STACK_DIR  /home/wolf/stack          remote compose stack dir
#   DEPLOY_DATA_DIR   /home/wolf/data/subtext   remote dir the DB is rsynced to (mounted :ro)
#   DEPLOY_BUILDER    discrepancies             buildx builder name
#   DEPLOY_BUILD_JOBS 2                         cap C++ build parallelism (lower=less RAM)
#   DEPLOY_SKIP_DB_SYNC unset                   set=1 to skip the DB rsync (code-only deploy)
#   DEPLOY_ALLOW_DIRTY unset                    set=1 to skip the clean-tree check

set -euo pipefail

# Always operate from the repo root (this script's directory).
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

# ── Configuration ─────────────────────────────────────────────────────────
APP="subtext"
PORT="3000"                                           # SUBTEXT_ADDR default port
DOMAIN="${DEPLOY_DOMAIN:-$APP.discrepancies.eu}"

SSH_HOST="${DEPLOY_SSH:-wolf@51.158.67.158}"
REGISTRY="${DEPLOY_REGISTRY:-rg.fr-par.scw.cloud}"
NAMESPACE="${DEPLOY_NAMESPACE:-discrepancies}"
IMAGE="${DEPLOY_IMAGE:-$REGISTRY/$NAMESPACE/$APP}"
TAG="${DEPLOY_TAG:-latest}"
STACK_DIR="${DEPLOY_STACK_DIR:-/home/wolf/stack}"
DATA_DIR="${DEPLOY_DATA_DIR:-/home/wolf/data/$APP}"   # remote dir bind-mounted read-only at /data
BUILDER="${DEPLOY_BUILDER:-discrepancies}"
PLATFORM="linux/amd64"                                # server is amd64; laptop may be arm64
BUILD_JOBS="${DEPLOY_BUILD_JOBS:-2}"                  # cap C++ compile parallelism (memory)

DB_FILE="data/subtext.duckdb"

say()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!!\033[0m  %s\n'  "$*" >&2; }
die()  { printf '\033[1;31mxx\033[0m  %s\n'  "$*" >&2; exit 1; }

# ── Preconditions ─────────────────────────────────────────────────────────
command -v docker >/dev/null || die "docker not found on PATH."
docker buildx version >/dev/null 2>&1 || die "docker buildx not available (needed for --platform builds)."

# A deploy must map to a real commit: refuse to build from a dirty tree.
if [ -z "${DEPLOY_ALLOW_DIRTY:-}" ]; then
  if ! git diff --quiet || ! git diff --cached --quiet; then
    die "working tree is dirty — commit/stash first so the image maps to a commit (or set DEPLOY_ALLOW_DIRTY=1)."
  fi
fi
GIT_SHA="$(git rev-parse --short=12 HEAD)"

# The DuckDB store is rsynced to the server and bind-mounted read-only (NOT baked
# into the image). It's the pipeline's output and is gitignored, so verify it
# exists locally before we try to sync it. (Skippable for a code-only deploy.)
if [ -z "${DEPLOY_SKIP_DB_SYNC:-}" ] && [ ! -f "$DB_FILE" ]; then
  die "$DB_FILE not found. Build it first with ./pipeline/run_ingest.sh, or set DEPLOY_SKIP_DB_SYNC=1 to deploy code only."
fi

IMG_LATEST="$IMAGE:$TAG"
IMG_SHA="$IMAGE:$GIT_SHA"

say "App:      $APP  (listens on 0.0.0.0:$PORT inside the container)"
say "Image:    $IMG_LATEST"
say "          $IMG_SHA"
say "Platform: $PLATFORM  (build jobs: $BUILD_JOBS)"
if [ -z "${DEPLOY_SKIP_DB_SYNC:-}" ]; then
  say "DB:       $DB_FILE ($(du -h "$DB_FILE" | cut -f1)) → $SSH_HOST:$DATA_DIR (mounted :ro)"
else
  say "DB:       sync skipped (DEPLOY_SKIP_DB_SYNC=1) — using whatever is already on the server"
fi

# ── Build + push (steps 1 & 2) ────────────────────────────────────────────
# One cross-arch buildx invocation builds for linux/amd64 and pushes both tags.
# On Apple Silicon this runs the amd64 build under emulation — expect the first
# build (which compiles bundled DuckDB) to be slow.
if ! docker buildx inspect "$BUILDER" >/dev/null 2>&1; then
  say "Creating buildx builder '$BUILDER' (docker-container driver)…"
  docker buildx create --name "$BUILDER" --driver docker-container >/dev/null
fi

say "Building + pushing (this is where a 401 would surface if not logged in)…"
BUILD_LOG="$(mktemp)"
trap 'rm -f "$BUILD_LOG"' EXIT

set +e
docker buildx build \
  --builder "$BUILDER" \
  --platform "$PLATFORM" \
  --build-arg "BUILD_JOBS=$BUILD_JOBS" \
  --tag "$IMG_LATEST" \
  --tag "$IMG_SHA" \
  --push \
  . 2>&1 | tee "$BUILD_LOG"
build_rc=${PIPESTATUS[0]}
set -e

if [ "$build_rc" -ne 0 ]; then
  if grep -qiE '401|unauthorized|authentication required|denied|forbidden' "$BUILD_LOG"; then
    warn "Registry rejected the push (looks like auth)."
    warn "Log in and retry:  docker login $REGISTRY"
  fi
  die "buildx build/push failed (exit $build_rc)."
fi
say "Pushed:  $IMG_LATEST"
say "         $IMG_SHA"

# ── Sync the DB to the host (mounted read-only into the container) ─────────
# The container gets the store from a bind mount, not the image, so ship it to
# the host first. rsync's quick check (size+mtime) makes re-runs a fast no-op
# when the DB hasn't changed; --partial resumes an interrupted large transfer.
# Old rsync-compatible flags (macOS ships rsync 2.6.9): no --info=progress2.
if [ -z "${DEPLOY_SKIP_DB_SYNC:-}" ]; then
  RSYNC_SSH="ssh -o BatchMode=yes -o ConnectTimeout=15"
  say "Ensuring $SSH_HOST:$DATA_DIR exists…"
  ssh -o BatchMode=yes -o ConnectTimeout=15 "$SSH_HOST" "mkdir -p '$DATA_DIR'"

  say "Syncing $DB_FILE → $SSH_HOST:$DATA_DIR/ (skips if unchanged; large files are slow)…"
  rsync -az --partial --progress -e "$RSYNC_SSH" "$DB_FILE" "$SSH_HOST:$DATA_DIR/"

  # Ship the Loughran-McDonald dictionary CSV(s) too, if present beside the DB —
  # the app looks for it in the DB's directory for inline word highlighting.
  shopt -s nullglob
  lm_csvs=(data/*.csv)
  shopt -u nullglob
  if [ "${#lm_csvs[@]}" -gt 0 ]; then
    say "Syncing dictionary CSV(s): ${lm_csvs[*]}"
    rsync -az --partial -e "$RSYNC_SSH" "${lm_csvs[@]}" "$SSH_HOST:$DATA_DIR/"
  fi
  say "DB in place on the host."
fi

# ── Roll only this service (step 3) ───────────────────────────────────────
# First-deploy chicken-and-egg: the service isn't in the stack's compose yet, so
# compose reports "no such service". Tolerate exactly that (and only that) — it
# means the image is pushed and you now wire the service + Caddy block into
# scaleway-infra. Every other roll failure hard-fails.
say "Rolling '$APP' on $SSH_HOST …"
ROLL_CMD="cd $STACK_DIR && docker compose pull $APP && docker compose up -d $APP"

set +e
roll_out="$(ssh -o BatchMode=yes -o ConnectTimeout=15 "$SSH_HOST" "$ROLL_CMD" 2>&1)"
roll_rc=$?
set -e
printf '%s\n' "$roll_out"

if [ "$roll_rc" -ne 0 ]; then
  if printf '%s' "$roll_out" | grep -qiE 'no such service'; then
    echo
    say "First-deploy bootstrap: the stack doesn't know '$APP' yet — that's expected."
    say "Image is in the registry:"
    say "    $IMG_LATEST"
    say "    $IMG_SHA"
    say "Next: add the service + Caddy block to scaleway-infra and run its deploy."
    say "(see the blocks printed below / in this repo's deploy notes)"
    exit 0
  fi
  die "roll failed on $SSH_HOST (exit $roll_rc) — see output above."
fi
say "Rolled '$APP' — container is running the new image."

# ── Report (best-effort; never fails the deploy) ──────────────────────────
URL="https://$DOMAIN"
echo
say "Container rolled. It will serve at:"
say "    $URL"
say "…once scaleway-infra's Caddy block for '$APP' is deployed. This script only"
say "rolls the container; it does not touch Caddy, so the URL may not route yet."
echo
say "Best-effort check (no response is normal until Caddy routes it):"
curl -sI --max-time 5 "$URL" 2>/dev/null | head -n 1 || true
echo
