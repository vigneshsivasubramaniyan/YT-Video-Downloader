FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
COPY static ./static
RUN mkdir -p /app/downloads
ENV DOWNLOAD_DIR=/app/downloads
EXPOSE 48201
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "48201"]
