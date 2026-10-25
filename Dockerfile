# API + built PWA in one image. NOTE: written for the docker-compose (Postgres/PostGIS) path; Docker was not
# available on the build machine, so this image has NOT been built or tested here (see docs/LIMITATIONS.md).
FROM node:22-slim AS web
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim
WORKDIR /app
COPY requirements.lock.txt ./
RUN pip install --no-cache-dir -r requirements.lock.txt "psycopg[binary]"
COPY . .
COPY --from=web /app/frontend/dist ./frontend/dist
ENV PYTHONPATH=/app/backend:/app PYTHONUTF8=1
EXPOSE 8000
CMD ["sh", "-c", "python -m app.cli load && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"]
