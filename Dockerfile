# Stage 1: Build React UI
FROM node:20-alpine AS ui-build
WORKDIR /build
COPY collection/ui/package*.json ./
RUN npm ci
COPY collection/ui/ ./
RUN npm run build

# Stage 2: Python API + built UI
FROM python:3.11-slim
WORKDIR /app

RUN pip install --no-cache-dir fastapi "uvicorn[standard]"

# Copy app code
COPY collection/__init__.py collection/api.py collection/schema.py ./collection/

# Copy built UI into the location api.py expects
COPY --from=ui-build /build/dist ./collection/ui/dist/

EXPOSE 8420
CMD ["python3", "-m", "uvicorn", "collection.api:app", "--host", "0.0.0.0", "--port", "8420"]
