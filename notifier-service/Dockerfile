FROM python:3.9-slim

WORKDIR /app

# Устанавливаем netcat для проверки соединения
RUN apt-get update && apt-get install -y netcat-traditional && rm -rf /var/lib/apt/lists/*

# Копируем requirements и устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем всё приложение
COPY . .

# Копируем скрипт ожидания Kafka и делаем его исполняемым
COPY wait-for-kafka.sh /app/wait-for-kafka.sh
RUN chmod +x /app/wait-for-kafka.sh

# Создаем папку logs и даем права
RUN mkdir -p /app/logs && chmod 777 /app/logs

# Создаем пользователя без прав root и назначаем владельца файлов
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8443
#EXPOSE 8000

# Устанавливаем ENTRYPOINT на скрипт ожидания Kafka
ENTRYPOINT ["/app/wait-for-kafka.sh"]
CMD ["kafka:9092", "60", "--", "python", "main.py"]
