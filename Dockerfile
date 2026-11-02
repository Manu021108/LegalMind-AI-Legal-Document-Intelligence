FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for PyMuPDF
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data directories
RUN mkdir -p uploads vector_db data

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD ["python", "healthcheck.py"]

# Run with uvicorn.
# NOTE: the FAISS vector store keeps its index in process memory, so run a
# single worker/process only. Scaling out requires a networked vector DB.
CMD ["python", "app.py"]
