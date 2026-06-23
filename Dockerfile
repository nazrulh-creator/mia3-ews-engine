# MIA3 Early Warning Engine — container image
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

# System deps for numpy/pandas/xgboost wheels are bundled; gcc kept minimal.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libgomp1 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080
# Web process. The scheduled scoring machine overrides CMD with:
#   python -m scripts.run_batch
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
