FROM python:3.11-slim

# Keep image small / reliable
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# (Optional) build tools for some wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential gcc libffi-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install deps first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY . .

# HF Spaces (Docker) provides $PORT (often 7860). Bind to it; default to 7860 locally.
EXPOSE 7860
CMD ["gunicorn","app:app","--bind","0.0.0.0:${PORT:-7860}","--workers","1","--threads","8","--worker-class","gthread","--timeout","180"]
