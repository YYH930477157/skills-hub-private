FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 SKILLHUB_DATA=/data
COPY pyproject.toml README.md ./
COPY skillhub ./skillhub
RUN pip install --no-cache-dir .
COPY --from=web /web/dist ./frontend/dist
EXPOSE 8000
VOLUME ["/data"]
CMD ["skillhub", "serve", "--host", "0.0.0.0", "--port", "8000"]
