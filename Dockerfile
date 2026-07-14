# syntax=docker/dockerfile:1
#
# Subtext — Leptos 0.8 SSR + Axum 0.8 server (Pattern A: reverse-proxied by Caddy).
# Build for the SERVER's arch: `docker buildx build --platform=linux/amd64 ...`
# (the deploy.sh does this; a plain `docker build` on Apple Silicon makes an
# arm64 image the amd64 server can't run).

# ---- build stage: compile the SSR binary ---------------------------------
# The duckdb crate's `bundled` feature compiles libduckdb (C++) from source, so
# the build image needs a full C/C++ toolchain. rust:1-bookworm is built on
# buildpack-deps and already ships build-essential.
FROM rust:1-bookworm AS build
WORKDIR /build

# Compiling bundled DuckDB (C++) is memory-hungry — each unity-build translation
# unit can need >1 GB, and it's worse under amd64 emulation on an arm64 laptop.
# Cap parallelism so peak RAM stays bounded and the build doesn't OOM the Docker
# VM ("cannot allocate memory"). Raise for a faster build if you have the RAM:
#   docker buildx build --build-arg BUILD_JOBS=4 …   (deploy.sh: DEPLOY_BUILD_JOBS=4)
ARG BUILD_JOBS=2
ENV CARGO_BUILD_JOBS=${BUILD_JOBS}

# Cache the expensive dependency compile (libduckdb-sys dominates the build) by
# compiling against the manifests with a stub main first; real sources come
# after, so day-to-day source edits don't recompile DuckDB.
COPY site/Cargo.toml site/Cargo.lock ./
RUN mkdir src \
 && echo 'fn main() { println!("stub"); }' > src/main.rs \
 && cargo build --release --locked \
 && rm -rf src

COPY site/src ./src
COPY site/style ./style
# Real build — deps stay cached from the layer above; only our crate recompiles.
#
# CRITICAL: BuildKit normalizes copied-file mtimes to a fixed past date, so cargo
# can think these real sources predate the stub binary built above and skip the
# rebuild — silently shipping the `println!("stub")` placeholder. `touch` the
# sources so their mtime is newer and cargo recompiles the real crate. Deleting
# the stub binary first turns any residual skip into a loud COPY failure below
# instead of a stub that boots and exits.
RUN rm -f target/release/subtext \
 && touch src/*.rs \
 && cargo build --release --locked

# Fetch the DuckDB `fts` extension that matches the bundled DuckDB version, so
# the runtime can LOAD it offline for BM25 search (the app calls `LOAD fts`; we
# don't want the container reaching extensions.duckdb.org per query). This is the
# official *signed* build, so a plain `LOAD fts` verifies and loads it — no
# allow_unsigned_extensions needed. The version/platform must match the path the
# runtime reports: if the duckdb crate is bumped, update DUCKDB_VERSION to the
# new "extensions/<version>/linux_amd64" the runtime asks for.
ARG DUCKDB_VERSION=v1.5.4
ARG DUCKDB_PLATFORM=linux_amd64
RUN set -eu; \
    dir="/duckdb-ext/${DUCKDB_VERSION}/${DUCKDB_PLATFORM}"; \
    rel="${DUCKDB_VERSION}/${DUCKDB_PLATFORM}/fts.duckdb_extension.gz"; \
    mkdir -p "$dir"; \
    curl -fsSL --retry 3 "https://extensions.duckdb.org/${rel}" -o /tmp/fts.gz \
      || curl -fsSL --retry 3 "http://extensions.duckdb.org/${rel}" -o /tmp/fts.gz; \
    gunzip -c /tmp/fts.gz > "$dir/fts.duckdb_extension"; \
    rm -f /tmp/fts.gz; \
    test -s "$dir/fts.duckdb_extension"

# ---- runtime stage: slim, non-root, DB baked in --------------------------
FROM debian:bookworm-slim AS runtime
# The binary dynamically links glibc + libstdc++ (from the bundled C++ objects);
# ca-certificates is harmless and lets DuckDB fetch an extension if it ever must.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates libstdc++6 \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --system --uid 10001 --create-home --home-dir /app app

WORKDIR /app
COPY --from=build /build/target/release/subtext /usr/local/bin/subtext

# Bake the fts extension where DuckDB looks for it: $HOME/.duckdb/extensions/
# <version>/<platform>/. HOME resolves to /app (the app user's home), which is
# exactly the path the runtime reported as missing. Enables the app's `LOAD fts`
# (BM25 search) offline.
COPY --from=build /duckdb-ext /app/.duckdb/extensions
RUN chown -R app:app /app/.duckdb

# The analytical store (~3.5 GB) is NOT baked into the image — that would make a
# ~3.6 GB image and needs ~7 GB transiently on the server to pull+extract, which
# overruns a small VM's disk. Instead it's bind-mounted read-only from the host
# at /data (see the compose block: `- /home/wolf/data/subtext:/data:ro`).
# deploy.sh rsyncs the DB there. The app opens it read-only (AccessMode::
# ReadOnly), so a :ro mount is correct. A Loughran-McDonald dictionary CSV placed
# beside the DB on the host is picked up for inline highlighting (optional).

# Bind 0.0.0.0 (NOT loopback) so the separate Caddy container can reach us —
# a 127.0.0.1 bind would give 502s. SUBTEXT_DB points at the mounted store.
ENV SUBTEXT_ADDR=0.0.0.0:3000 \
    SUBTEXT_DB=/data/subtext.duckdb

USER app
EXPOSE 3000
CMD ["subtext"]
