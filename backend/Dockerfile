# ShadowMap backend image (includes FFmpeg for video mode). Build from the project root:
#   docker build -f backend/Dockerfile -t shadowmap-backend .
FROM python:3.14-slim

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app/backend
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Code and the saved OpenStreetMap data (assets/demo-data). Night-ride videos are not part of the image.
COPY backend/app ./app
COPY backend/scripts ./scripts
COPY assets/demo-data /app/assets/demo-data

# Data (database, photos, uploads) lives on a persistent disk mounted at /var/data.
ENV DATA_DIR=/var/data \
    DATABASE_URL=sqlite:////var/data/shadowmap.db \
    PYTHONUNBUFFERED=1
EXPOSE 8000

# One process only: the walk clock, video queue and duplicate lock assume a single server process.
CMD ["sh", "-c", "mkdir -p $DATA_DIR && python -m scripts.build_map --if-empty && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --proxy-headers"]
