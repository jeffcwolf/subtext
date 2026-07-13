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
#   DEPLOY_BUILDER    discrepancies             buildx builder name
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
BUILDER="${DEPLOY_BUILDER:-discrepancies}"
PLATFORM="linux/amd64"                                # server is amd64; laptop may be arm64

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

# The DuckDB store is baked into the image (see Dockerfile). It's the pipeline's
# output and is gitignored, so verify it exists locally before building.
if [ ! -f "$DB_FILE" ]; then
  die "$DB_FILE not found. Build it first with ./pipeline/run_ingest.sh (it's baked into the image)."
fi

IMG_LATEST="$IMAGE:$TAG"
IMG_SHA="$IMAGE:$GIT_SHA"

say "App:      $APP  (listens on 0.0.0.0:$PORT inside the container)"
say "Image:    $IMG_LATEST"
say "          $IMG_SHA"
say "Platform: $PLATFORM"
say "DB:       $DB_FILE ($(du -h "$DB_FILE" | cut -f1)) — baked into the image"

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
