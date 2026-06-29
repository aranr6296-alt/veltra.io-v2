FROM python:3.11-slim

# Install ffmpeg and libsodium (required for discord.py voice)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsodium-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]
