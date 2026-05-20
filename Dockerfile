FROM python:3.11-slim

WORKDIR /app

# Install system dependencies if any are needed (e.g. gcc for some python packages, though sqlite/sqlalchemy don't strictly require it)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x entrypoint.sh

ENTRYPOINT ["./entrypoint.sh"]
