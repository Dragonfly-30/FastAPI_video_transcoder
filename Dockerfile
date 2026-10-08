FROM python:3.12-slim

# Install system dependencies (FFmpeg for video processing, curl for health checks)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . .

EXPOSE 8000

# Default command runs the FastAPI web server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
