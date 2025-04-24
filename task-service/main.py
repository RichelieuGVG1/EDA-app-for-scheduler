from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from datetime import datetime
import redis
from kafka import KafkaProducer
import json
import os
from prometheus_client import Counter, Histogram, start_http_server
import time
from dotenv import load_dotenv

load_dotenv()
app = FastAPI()

# Prometheus metrics
TASKS_CREATED = Counter('tasks_created_total', 'Total number of tasks created')
TASKS_RETRIEVED = Counter('tasks_retrieved_total', 'Total number of tasks retrieved')
TASK_LATENCY = Histogram('task_operation_latency_seconds', 'Task operation latency')

# Redis connection
redis_client = redis.Redis(
    host=os.getenv('REDIS_HOST', 'localhost'),
    port=6379,
    decode_responses=True
)

# Kafka producer
producer = KafkaProducer(
    bootstrap_servers=os.getenv('KAFKA_BROKER', 'localhost:9092'),
    value_serializer=lambda v: json.dumps(v).encode('utf-8')
)

class Task(BaseModel):
    title: str
    description: str
    due_date: datetime
    user_id: str

@app.on_event("startup")
async def startup_event():
    start_http_server(8001)

@app.post("/tasks/")
@TASK_LATENCY.time()
async def create_task(task: Task):
    task_id = str(int(time.time()))
    task_data = task.dict()
    task_data['id'] = task_id
    
    # Store in Redis with TTL
    redis_client.setex(
        f"task:{task_id}",
        3600,  # 1 hour TTL
        json.dumps(task_data, default=str)
    )
    
    # Publish event to Kafka
    producer.send('task_created', value=task_data)
    
    TASKS_CREATED.inc()
    return {"task_id": task_id, **task_data}

@app.get("/tasks/{task_id}")
@TASK_LATENCY.time()
async def get_task(task_id: str):
    task_data = redis_client.get(f"task:{task_id}")
    if not task_data:
        raise HTTPException(status_code=404, detail="Task not found")
    
    TASKS_RETRIEVED.inc()
    return json.loads(task_data)

@app.get("/health")
async def health_check():
    return {"status": "healthy"} 