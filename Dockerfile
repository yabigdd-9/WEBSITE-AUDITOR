FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libsqlite3-dev \
    bash \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for caching
COPY money-machine/requirements*.txt ./money-machine/

# Install Python dependencies
RUN pip install --no-cache-dir -r money-machine/requirements-email.txt \
    && pip install --no-cache-dir pyyaml exa-py

# Copy project files
COPY money-machine/ ./money-machine/
RUN mkdir -p /app/config
COPY money-machine/config/disposable_email_blocklist.conf /app/config/
COPY money-machine/config/disposable_email_blocklist.source.json /app/config/
COPY database/ ./database/
COPY .env ./

# Create evidence directory
RUN mkdir -p evidence/exa reports/daily-operator

# Set environment
ENV PYTHONPATH=/app
ENV MM_ROOT=/app

WORKDIR /app/money-machine

ENTRYPOINT ["python3", "mm_operator.py"]
CMD ["--help"]
