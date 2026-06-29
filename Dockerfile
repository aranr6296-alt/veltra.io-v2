FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libopus0 \
    libopus-dev \
    libsodium23 \
    libsodium-dev \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir \
    "discord.py[voice]>=2.3.2" \
    "PyNaCl>=1.5.0" \
    "yt-dlp>=2024.1.1" \
    "aiohttp>=3.9.0" \
    "python-dotenv>=1.0.0"

COPY . .

CMD ["python", "-u", "main.py"]
