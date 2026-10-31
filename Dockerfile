# ShadowMap in ONE container (Hugging Face Spaces): the backend serves the API and the built React app on port 7860.
# Build from the project root: docker build -t shadowmap .   (backend/Dockerfile is the separate Render backend.)

# Stage 1: build the React app into frontend/dist
FROM node:20-alpine AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Python backend (3.12: the pinned numpy has no 3.11 build) + FFmpeg for video mode
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/backend
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Code, YuNet face-blur weights and the saved OpenStreetMap data. Night-ride videos are never part of the image.
COPY backend/app ./app
COPY backend/scripts ./scripts
COPY backend/models ./models
COPY assets/demo-data /app/assets/demo-data
COPY --from=frontend /build/dist /app/frontend/dist

# A fresh database built from the saved map data (the laptop's database holds walks/contacts and is not copied).
# Hugging Face runs the container as user 1000: it must be able to write the database, photos and video frames.
RUN python -m scripts.build_map --all --if-empty && chmod -R 777 /app

ENV FRONTEND_DIST=/app/frontend/dist \
    DEMO_MODE=true \
    API_DOCS=false \
    PYTHONUNBUFFERED=1
EXPOSE 7860

# One process only: the walk clock, video queue and duplicate lock assume a single server process.
# Port: 7860 (Hugging Face), or the host's PORT setting (Render's free plan sets one).
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-7860} --workers 1 --proxy-headers --forwarded-allow-ips '*'"]
