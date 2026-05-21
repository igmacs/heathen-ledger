FROM python:3.11-slim

WORKDIR /app

# Install system dependencies if any are needed (e.g. gcc for some python packages, though sqlite/sqlalchemy don't strictly require it)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy packaging configuration files first to cache dependency installation
COPY pyproject.toml README.md ./

# Create dummy source package structure so pip install . doesn't fail
RUN mkdir -p src/heathen_ledger && touch src/heathen_ledger/__init__.py

# Install project dependencies
RUN pip install --no-cache-dir .

# Copy the rest of the application files
COPY . .

# Re-install the actual application package without installing dependencies again
RUN pip install --no-cache-dir --no-deps .

RUN chmod +x entrypoint.sh

ENTRYPOINT ["./entrypoint.sh"]
