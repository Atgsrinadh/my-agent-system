# Universal Dockerfile — works on Railway, Render, Fly.io, or any Docker host.
FROM python:3.11-slim

WORKDIR /app

# System deps needed for PyMuPDF, pandas, etc.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Railway/Render set $PORT automatically; default for local/other hosts
ENV PORT=8000
EXPOSE 8000

CMD ["python", "main.py"]
