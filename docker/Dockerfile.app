# Dockerfile for the FastAPI backend and Streamlit UI.
# The sandbox image (docker/Dockerfile) is built separately.
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
COPY ui/ ./ui/
COPY benchmarks/ ./benchmarks/

# FastAPI: override CMD at runtime for the Streamlit service
EXPOSE 8000 8501
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
