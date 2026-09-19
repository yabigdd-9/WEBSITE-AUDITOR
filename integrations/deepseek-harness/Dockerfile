FROM node:22-bookworm-slim

ARG DSH_VERSION=0.1.6-alpha.2

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates curl git openssl python3 python3-pip python3-venv \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g "@deepseek-ai/dsh@${DSH_VERSION}" pnpm

ENV DSH_HOME=/dsh-home \
    DSH_TELEMETRY_MODE=DISABLED \
    OLLAMA_API_KEY=ollama \
    WEBSITE_AUDITOR_ROOT=/workspace

WORKDIR /workspace

CMD ["bash"]
