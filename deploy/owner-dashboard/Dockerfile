FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY auditor_toolkit ./auditor_toolkit
COPY website_auditor ./website_auditor
COPY scripts ./scripts
RUN pip install --no-cache-dir '.[portal,postgres,vault]' \
    && useradd --uid 10001 --create-home portal
USER portal
ENV MM_PAID_ALLOWED=0 MM_ALLOW_EXTERNAL_FREE_MODELS=0 MM_EXTERNAL_SEND_ALLOWED=0
EXPOSE 8000
CMD ["uvicorn", "auditor_toolkit.hosted_portal:create_hosted_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
