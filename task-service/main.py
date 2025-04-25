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
from typing import List, Optional
import uuid

load_dotenv()

# Swagger metadata
app = FastAPI(
    title="Task Management Service",
    description="Service for managing tasks with CQRS and Event Sourcing",
    version="1.0.0",
    docs_url="/docs",  # Swagger UI
    redoc_url="/redoc",  # ReDoc
    openapi_url="/openapi.json"  # OpenAPI schema
)

# Prometheus metrics
TASKS_CREATED = Counter('tasks_created_total', 'Total number of tasks created')
TASKS_RETRIEVED = Counter('tasks_retrieved_total', 'Total number of tasks retrieved')
TASK_LATENCY = Histogram('task_operation_latency_seconds', 'Task operation latency')

# Redis connections
# Command DB (Write Model)
command_db = redis.Redis(
    host=os.getenv('REDIS_HOST', 'localhost'),
    port=6379,
    db=0,
    decode_responses=True
)

# Query DB (Read Model)
query_db = redis.Redis(
    host=os.getenv('REDIS_HOST', 'localhost'),
    port=6379,
    db=1,
    decode_responses=True
)

# Event Store
event_store = redis.Redis(
    host=os.getenv('REDIS_HOST', 'localhost'),
    port=6379,
    db=2,
    decode_responses=True
)

# Kafka producer for events
producer = KafkaProducer(
    bootstrap_servers=os.getenv('KAFKA_BROKER', 'localhost:9092'),
    value_serializer=lambda v: json.dumps(v).encode('utf-8')
)

class Task(BaseModel):
    """Task model for creating and updating tasks"""
    title: str
    description: str
    due_date: datetime
    user_id: str

    class Config:
        schema_extra = {
            "example": {
                "title": "Complete project documentation",
                "description": "Write comprehensive documentation for the task management system",
                "due_date": "2024-03-20T15:00:00",
                "user_id": "user123"
            }
        }

class TaskEvent(BaseModel):
    """Event model for task-related events"""
    event_id: str
    event_type: str
    task_id: str
    timestamp: datetime
    data: dict

class TaskQuery(BaseModel):
    """Query model for task data"""
    task_id: str
    title: str
    description: str
    due_date: datetime
    user_id: str
    status: str
    created_at: datetime
    updated_at: datetime

# Event Handlers
def handle_task_created(event: TaskEvent):
    """Handle task creation event"""
    # Update read model
    task_data = event.data
    task_query = TaskQuery(
        task_id=event.task_id,
        title=task_data['title'],
        description=task_data['description'],
        due_date=datetime.fromisoformat(task_data['due_date']),
        user_id=task_data['user_id'],
        status='active',
        created_at=datetime.fromisoformat(event.timestamp),
        updated_at=datetime.fromisoformat(event.timestamp)
    )
    
    query_db.hmset(
        f"task:{event.task_id}",
        task_query.dict()
    )

def handle_task_updated(event: TaskEvent):
    """Handle task update event"""
    # Update read model
    task_data = event.data
    existing_task = query_db.hgetall(f"task:{event.task_id}")
    
    if existing_task:
        task_query = TaskQuery(
            task_id=event.task_id,
            title=task_data.get('title', existing_task[b'title'].decode()),
            description=task_data.get('description', existing_task[b'description'].decode()),
            due_date=datetime.fromisoformat(task_data.get('due_date', existing_task[b'due_date'].decode())),
            user_id=task_data.get('user_id', existing_task[b'user_id'].decode()),
            status=existing_task[b'status'].decode(),
            created_at=datetime.fromisoformat(existing_task[b'created_at'].decode()),
            updated_at=datetime.fromisoformat(event.timestamp)
        )
        
        query_db.hmset(
            f"task:{event.task_id}",
            task_query.dict()
        )

def handle_task_completed(event: TaskEvent):
    """Handle task completion event"""
    # Update read model
    existing_task = query_db.hgetall(f"task:{event.task_id}")
    
    if existing_task:
        task_query = TaskQuery(
            task_id=event.task_id,
            title=existing_task[b'title'].decode(),
            description=existing_task[b'description'].decode(),
            due_date=datetime.fromisoformat(existing_task[b'due_date'].decode()),
            user_id=existing_task[b'user_id'].decode(),
            status='completed',
            created_at=datetime.fromisoformat(existing_task[b'created_at'].decode()),
            updated_at=datetime.fromisoformat(event.timestamp)
        )
        
        query_db.hmset(
            f"task:{event.task_id}",
            task_query.dict()
        )

# Event Store Functions
def save_event(event: TaskEvent):
    """Save event to event store"""
    event_store.lpush(f"events:{event.task_id}", json.dumps(event.dict()))
    event_store.lpush("events:all", json.dumps(event.dict()))

def get_events(task_id: str) -> List[TaskEvent]:
    """Get all events for a task"""
    events = event_store.lrange(f"events:{task_id}", 0, -1)
    return [TaskEvent(**json.loads(event)) for event in events]

# Command Handlers
@app.post("/tasks/", 
    response_model=dict,
    summary="Create a new task",
    description="Create a new task with the provided details",
    tags=["Tasks"])
@TASK_LATENCY.time()
async def create_task(task: Task):
    """
    Create a new task.
    
    - **title**: Task title
    - **description**: Task description
    - **due_date**: Task due date
    - **user_id**: User ID who owns the task
    
    Returns the created task with its ID.
    """
    task_id = str(uuid.uuid4())
    event = TaskEvent(
        event_id=str(uuid.uuid4()),
        event_type="TaskCreated",
        task_id=task_id,
        timestamp=datetime.now().isoformat(),
        data=task.dict()
    )
    
    # Save event
    save_event(event)
    
    # Handle event
    handle_task_created(event)
    
    # Publish event to Kafka
    producer.send('task_created', value=event.dict())
    
    TASKS_CREATED.inc()
    return {"task_id": task_id, **task.dict()}

@app.put("/tasks/{task_id}",
    response_model=dict,
    summary="Update a task",
    description="Update an existing task with new details",
    tags=["Tasks"])
@TASK_LATENCY.time()
async def update_task(task_id: str, task: Task):
    """
    Update an existing task.
    
    - **task_id**: ID of the task to update
    - **task**: New task details
    
    Returns the status of the update operation.
    """
    event = TaskEvent(
        event_id=str(uuid.uuid4()),
        event_type="TaskUpdated",
        task_id=task_id,
        timestamp=datetime.now().isoformat(),
        data=task.dict()
    )
    
    # Save event
    save_event(event)
    
    # Handle event
    handle_task_updated(event)
    
    return {"status": "updated", "task_id": task_id}

@app.post("/tasks/{task_id}/complete",
    response_model=dict,
    summary="Complete a task",
    description="Mark a task as completed",
    tags=["Tasks"])
@TASK_LATENCY.time()
async def complete_task(task_id: str):
    """
    Mark a task as completed.
    
    - **task_id**: ID of the task to complete
    
    Returns the status of the completion operation.
    """
    event = TaskEvent(
        event_id=str(uuid.uuid4()),
        event_type="TaskCompleted",
        task_id=task_id,
        timestamp=datetime.now().isoformat(),
        data={}
    )
    
    # Save event
    save_event(event)
    
    # Handle event
    handle_task_completed(event)
    
    return {"status": "completed", "task_id": task_id}

# Query Handlers
@app.get("/tasks/{task_id}",
    response_model=dict,
    summary="Get a task",
    description="Retrieve a task by its ID",
    tags=["Tasks"])
@TASK_LATENCY.time()
async def get_task(task_id: str):
    """
    Get a task by ID.
    
    - **task_id**: ID of the task to retrieve
    
    Returns the task details if found.
    """
    task_data = query_db.hgetall(f"task:{task_id}")
    if not task_data:
        raise HTTPException(status_code=404, detail="Task not found")
    
    TASKS_RETRIEVED.inc()
    return {
        key.decode(): value.decode() 
        for key, value in task_data.items()
    }

@app.get("/tasks/{task_id}/history",
    response_model=List[dict],
    summary="Get task history",
    description="Retrieve the history of events for a task",
    tags=["Tasks"])
async def get_task_history(task_id: str):
    """
    Get the history of events for a task.
    
    - **task_id**: ID of the task
    
    Returns a list of events that affected the task.
    """
    events = get_events(task_id)
    return [event.dict() for event in events]

@app.get("/health",
    response_model=dict,
    summary="Health check",
    description="Check if the service is healthy",
    tags=["System"])
async def health_check():
    """
    Check if the service is healthy.
    
    Returns the health status of the service.
    """
    return {"status": "healthy"}

@app.on_event("startup")
async def startup_event():
    start_http_server(8001) 