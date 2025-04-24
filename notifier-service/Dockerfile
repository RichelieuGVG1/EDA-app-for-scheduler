FROM python:3.9-slim

WORKDIR /app

# Install netcat for wait script
RUN apt-get update && apt-get install -y netcat-traditional && rm -rf /var/lib/apt/lists/*

# Create logs directory with proper permissions
RUN mkdir -p /app/logs && chmod 777 /app/logs

# Copy wait script and make it executable
COPY wait-for-kafka.sh /wait-for-kafka.sh
RUN chmod +x /wait-for-kafka.sh

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

EXPOSE 8443

# Run as non-root user
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# Use wait script to ensure Kafka is ready before starting the application
CMD ["/wait-for-kafka.sh", "kafka", "9092", "python", "main.py"] 