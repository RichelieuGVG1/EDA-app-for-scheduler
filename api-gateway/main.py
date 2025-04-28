from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import httpx
import os
from prometheus_client import Counter, Histogram, start_http_server
import time

app = FastAPI()

# Prometheus metrics
REQUESTS_TOTAL = Counter('api_requests_total', 'Total number of API requests')
REQUEST_LATENCY = Histogram('api_request_latency_seconds', 'API request latency')

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Task service URL
TASK_SERVICE_URL = os.getenv('TASK_SERVICE_URL', 'http://task-service:8000')

@app.on_event("startup")
async def startup_event():
    # Start Prometheus metrics server on port 8001
    start_http_server(8001)
    print(f"Prometheus metrics server started on port 8001")  # For debugging
    # You might want to use proper logging here in production

@app.post("/tasks/")
@REQUEST_LATENCY.time()
async def create_task(task: dict):
    REQUESTS_TOTAL.inc()
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(f"{TASK_SERVICE_URL}/tasks/", json=task)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            raise HTTPException(status_code=e.response.status_code, detail=e.response.text)

@app.get("/tasks/{task_id}")
@REQUEST_LATENCY.time()
async def get_task(task_id: str):
    REQUESTS_TOTAL.inc()
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{TASK_SERVICE_URL}/tasks/{task_id}")
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            raise HTTPException(status_code=e.response.status_code, detail=e.response.text)

@app.get("/health")
async def health_check():
    return {"status": "healthy"}