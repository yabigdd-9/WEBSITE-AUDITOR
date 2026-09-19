FROM node:22-bookworm-slim

ARG DSH_VERSION=0.1.6-alpha.2
ARG NONROOT_USER=dsh-worker
ARG NONROOT_UID=1000

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates curl git openssl python3 python3-pip python3-venv \
    && rm -rf /var/lib/apt/lists/*

# Non-root user so the Harness process cannot accidentally touch host state
# even if a container escape or misconfiguration occurs.
RUN groupadd --gid "${NONROOT_UID}" "${NONROOT_USER}" \
    && useradd --uid "${NONROOT_UID}" --gid "${NONROOT_UID}" \
       --create-home --shell /usr/sbin/nologin \
       "${NONROOT_USER}"

RUN npm install -g "@deepseek-ai/dsh@${DSH_VERSION}" pnpm \
    && corepack enable \
    && corepack prepare pnpm@latest --activate

ENV DSH_HOME=/dsh-home \
    DSH_TELEMETRY_MODE=DISABLED \
    OLLAMA_API_KEY=ollama \
    WEBSITE_AUDITOR_ROOT=/workspace

WORKDIR /workspace
COPY --chown="${NONROOT_USER}:${NONROOT_USER}" . /workspace

USER "${NONROOT_USER}"

CMD ["bash"]
