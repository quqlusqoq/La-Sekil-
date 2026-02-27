FROM python:3.10-slim

WORKDIR /app

# Установка FFmpeg
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Копирование зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование кода
COPY sekilebot.py .

# Запуск бота
CMD ["python", "sekilebot.py"]