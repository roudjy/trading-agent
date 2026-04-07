FROM python:3.11-slim

WORKDIR /app

# Systeem dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Project bestanden
COPY . .

# Maak mappen aan
RUN mkdir -p logs reports

# Pre-maak yfinance cache directory aan zodat concurrent initialisatie geen EEXIST error geeft
RUN mkdir -p /root/.cache/py-yfinance

CMD ["python", "run.py"]
