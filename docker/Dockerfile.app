# Stage 1: Build the React frontend
FROM node:20-slim AS frontend-builder

WORKDIR /build
COPY ui/package*.json ./
RUN npm install

COPY ui/ ./
RUN npm run build

# Stage 2: Build the FastAPI backend
FROM python:3.11-slim

# Install uv for fast dependency resolution
RUN pip install --no-cache-dir uv==0.4.29

WORKDIR /app

# Copy dependency manifests first to exploit layer caching
COPY pyproject.toml uv.lock ./

# Install project dependencies (no dev extras)
RUN uv pip install --system --no-cache -e "."

# Copy application source
COPY app/ ./app/
COPY benchmarks/ ./benchmarks/

# Copy built frontend from Stage 1
COPY --from=frontend-builder /build/dist ./ui/dist

# FastAPI
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
