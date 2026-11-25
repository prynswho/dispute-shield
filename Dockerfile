FROM node:25.8.1-slim AS frontend
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/index.html frontend/vite.config.js ./
COPY frontend/src ./src
RUN npm run build

FROM python:3.14.3-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    DISPUTE_ARTIFACT_DIR=/app/artifacts DISPUTE_FRONTEND_DIR=/app/frontend/dist \
    DISPUTE_UPLOAD_DIR=/data/uploads OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
COPY backend/requirements-runtime.txt ./backend/requirements-runtime.txt
RUN pip install --no-cache-dir -r backend/requirements-runtime.txt
COPY backend/app ./backend/app
COPY backend/scripts/*.py ./backend/scripts/
COPY artifacts ./artifacts
COPY --from=frontend /build/dist ./frontend/dist
CMD ["sh", "-c", "exec uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port ${PORT:-8000}"]
