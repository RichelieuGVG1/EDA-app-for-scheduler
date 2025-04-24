from kafka import KafkaConsumer, KafkaProducer
import redis
import json
import os
from datetime import datetime
import time
from prometheus_client import Counter, start_http_server
import schedule
from dotenv import load_dotenv

load_dotenv()
# Prometheus metrics
REMINDERS_SCHEDULED = Counter('reminders_scheduled_total', 'Total number of reminders scheduled')
REMINDERS_SENT = Counter('reminders_sent_total', 'Total number of reminders sent')

# Redis connection
redis_client = redis.Redis(
    host=os.getenv('REDIS_HOST', 'localhost'),
    port=6379,
    decode_responses=True
)

# Kafka consumer for task_created events
consumer = KafkaConsumer(
    'task_created',
    bootstrap_servers=os.getenv('KAFKA_BROKER', 'localhost:9092'),
    value_deserializer=lambda m: json.loads(m.decode('utf-8'))
)

# Kafka producer for task_due_soon events
producer = KafkaProducer(
    bootstrap_servers=os.getenv('KAFKA_BROKER', 'localhost:9092'),
    value_serializer=lambda v: json.dumps(v).encode('utf-8')
)

def process_task_created(task):
    task_id = task['id']
    due_date = datetime.fromisoformat(task['due_date'])
    
    # Store task in Redis with TTL until due date
    ttl = int((due_date - datetime.now()).total_seconds())
    if ttl > 0:
        redis_client.setex(
            f"task:{task_id}",
            ttl,
            json.dumps(task)
        )
        REMINDERS_SCHEDULED.inc()

def check_due_tasks():
    current_time = datetime.now()
    for key in redis_client.scan_iter("task:*"):
        task_data = json.loads(redis_client.get(key))
        due_date = datetime.fromisoformat(task_data['due_date'])
        
        # If task is due within 1 hour
        if 0 < (due_date - current_time).total_seconds() <= 3600:
            producer.send('task_due_soon', value=task_data)
            REMINDERS_SENT.inc()

def main():
    # Start Prometheus metrics server
    start_http_server(8001)
    
    # Schedule task checking every minute
    schedule.every(1).minutes.do(check_due_tasks)
    
    # Process task_created events
    for message in consumer:
        process_task_created(message.value)
    
    # Run the scheduler
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    main() 