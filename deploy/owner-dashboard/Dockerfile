FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml README.md requirements-hosted-runtime.txt ./
RUN pip install --no-cache-dir --only-binary=:all: --require-hashes -r requirements-hosted-runtime.txt
COPY auditor_toolkit ./auditor_toolkit
COPY website_auditor ./website_auditor
COPY scripts ./scripts
RUN python -m scripts.install_reviewed_package \
    && useradd --uid 10001 --create-home portal
USER portal
ENV MM_PAID_ALLOWED=0 MM_ALLOW_EXTERNAL_FREE_MODELS=0 MM_EXTERNAL_SEND_ALLOWED=0
EXPOSE 8000
CMD ["uvicorn", "auditor_toolkit.hosted_portal:create_hosted_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
