# syntax=docker/dockerfile:1.7

# --- Stage 1: build the React SPA bundle. ----------------------------------
FROM node:20-alpine AS frontend_build
WORKDIR /frontend

# Install dependencies first (cache-friendly layer).
COPY frontend/package.json frontend/package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

# Then copy the source and build.
COPY frontend/ ./
RUN npm run build

# --- Stage 2: Python runtime (agent + dashboard share this image). ---------
FROM python:3.11-slim

WORKDIR /app

# System dependencies.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Project files.
COPY . .

# Pull in the pre-built React bundle so Flask can serve it on "/".
COPY --from=frontend_build /frontend/dist /app/frontend/dist

# Runtime dirs.
RUN mkdir -p logs reports state /root/.cache/py-yfinance

# Default command (agent). docker-compose overrides for the dashboard.
CMD ["python", "run.py"]
