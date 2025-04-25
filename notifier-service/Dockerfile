FROM python:3.9-slim

WORKDIR /app

# Install netcat for wait script
RUN apt-get update && apt-get install -y netcat-traditional && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Create logs directory and set permissions
RUN mkdir -p /app/logs && chmod 777 /app/logs

# Make wait script executable
RUN chmod +x /app/wait-for-kafka.sh

# Run as non-root user
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8443

# Use the wait script to ensure Kafka is ready
ENTRYPOINT ["/app/wait-for-kafka.sh"]
CMD ["kafka", "9092", "60", "--", "python", "main.py"]

