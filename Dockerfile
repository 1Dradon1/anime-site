FROM python:3.13-slim

WORKDIR /app

# Install system dependencies for ffmpeg and other media operations
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Environment variables will be handled by .env or docker-compose
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "5555"]
