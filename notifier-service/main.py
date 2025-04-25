import os
import logging
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.enums import ParseMode
from faststream.kafka import KafkaBroker
import json
import redis
from datetime import datetime
import ssl
import certifi
from prometheus_client import Counter, start_http_server
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiohttp import web
import threading
from dotenv import load_dotenv
from kafka import KafkaConsumer

load_dotenv()

# Configure logging
def setup_logging():
    # Create logs directory if it doesn't exist
    os.makedirs('/app/logs', exist_ok=True)
    
    # Create a unique log file name based on timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = f'/app/logs/bot_{timestamp}.log'
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    
    return logging.getLogger(__name__)

logger = setup_logging()

# Prometheus metrics
NOTIFICATIONS_SENT = Counter('notifications_sent_total', 'Total number of notifications sent')
TASKS_CREATED = Counter('tasks_created_total', 'Total number of tasks created via bot')
TASKS_LISTED = Counter('tasks_listed_total', 'Total number of task listings')

# Load environment variables
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable is not set")

REDIS_HOST = os.getenv('REDIS_HOST', 'redis')
REDIS_PORT = int(os.getenv('REDIS_PORT', '6379'))
KAFKA_SERVER = os.getenv('KAFKA_SERVER', 'kafka:9092')

logger.info(f"Initializing bot with token: {TELEGRAM_BOT_TOKEN[:10]}...")
logger.info(f"Redis host: {REDIS_HOST}")
logger.info(f"Redis port: {REDIS_PORT}")
logger.info(f"Kafka server: {KAFKA_SERVER}")

# Initialize Redis client
try:
    redis_client = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=0,
        socket_timeout=5,
        socket_connect_timeout=5,
        retry_on_timeout=True
    )
    redis_client.ping()  # Test connection
    logger.info("Successfully connected to Redis")
except Exception as e:
    logger.error(f"Failed to connect to Redis: {str(e)}")
    raise

# Initialize bot and dispatcher
bot = Bot(token=TELEGRAM_BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot=bot, storage=storage)

# Initialize Kafka broker
kafka_broker = KafkaBroker(KAFKA_SERVER)

# Keyboard setup
keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📝 Create Task")],
        [KeyboardButton(text="📋 List Tasks")],
        [KeyboardButton(text="❌ Delete Task")]
    ],
    resize_keyboard=True
)

# States
class TaskStates(StatesGroup):
    waiting_for_title = State()
    waiting_for_description = State()
    waiting_for_due_date = State()

# Kafka consumer setup
def create_kafka_consumer():
    logger.info("Creating Kafka consumer...")
    consumer = KafkaConsumer(
        'task_due_soon',
        bootstrap_servers=os.getenv('KAFKA_BROKER', 'localhost:9092'),
        group_id='telegram-notifier-bot',
        auto_offset_reset='earliest',
        enable_auto_commit=True,
        value_deserializer=lambda x: json.loads(x.decode('utf-8')),
        security_protocol='PLAINTEXT',
        api_version=(2, 0, 2)
    )
    logger.info("Kafka consumer created successfully")
    return consumer

# Command handlers
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    await message.answer(
        "👋 Welcome to Task Manager Bot!\n\n"
        "Use /newtask to create a new task\n"
        "Use /mytasks to view your tasks\n"
        "Use /help to see all available commands"
    )
    logger.info(f"User {user_id} started the bot")

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    help_text = (
        "📋 Available commands:\n\n"
        "/start - Start the bot\n"
        "/newtask - Create a new task\n"
        "/mytasks - View your tasks\n"
        "/help - Show this help message"
    )
    await message.answer(help_text)
    logger.info(f"Help command used by user {message.from_user.id}")

@dp.message(Command("newtask"))
async def cmd_new_task(message: types.Message, state: FSMContext):
    await state.set_state(TaskStates.waiting_for_title)
    await message.answer("Please enter the task title:")
    logger.info(f"User {message.from_user.id} started creating a new task")

@dp.message(TaskStates.waiting_for_title)
async def process_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text)
    await state.set_state(TaskStates.waiting_for_description)
    await message.answer("Please enter the task description:")

@dp.message(TaskStates.waiting_for_description)
async def process_description(message: types.Message, state: FSMContext):
    await state.update_data(description=message.text)
    await state.set_state(TaskStates.waiting_for_due_date)
    await message.answer("Please enter the due date (YYYY-MM-DD):")

@dp.message(TaskStates.waiting_for_due_date)
async def process_due_date(message: types.Message, state: FSMContext):
    try:
        due_date = datetime.strptime(message.text, '%Y-%m-%d')
        data = await state.get_data()
        task_data = {
            'user_id': message.from_user.id,
            'title': data['title'],
            'description': data['description'],
            'due_date': due_date.strftime('%Y-%m-%d'),
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        # Store task in Redis
        task_key = f"task:{message.from_user.id}:{datetime.now().timestamp()}"
        redis_client.hmset(task_key, task_data)
        
        await message.answer(
            f"✅ Task created successfully!\n\n"
            f"Title: {data['title']}\n"
            f"Description: {data['description']}\n"
            f"Due Date: {message.text}"
        )
        logger.info(f"Task created for user {message.from_user.id}")
        
    except ValueError:
        await message.answer("Invalid date format. Please use YYYY-MM-DD")
        return
    
    await state.clear()

@dp.message(Command("mytasks"))
async def cmd_my_tasks(message: types.Message):
    user_id = message.from_user.id
    tasks = []
    
    # Get all task keys for the user
    for key in redis_client.scan_iter(f"task:{user_id}:*"):
        task_data = redis_client.hgetall(key)
        if task_data:
            tasks.append({
                'title': task_data[b'title'].decode('utf-8'),
                'description': task_data[b'description'].decode('utf-8'),
                'due_date': task_data[b'due_date'].decode('utf-8')
            })
    
    if tasks:
        response = "📋 Your Tasks:\n\n"
        for i, task in enumerate(tasks, 1):
            response += (
                f"{i}. {task['title']}\n"
                f"   Description: {task['description']}\n"
                f"   Due Date: {task['due_date']}\n\n"
            )
    else:
        response = "You don't have any tasks yet. Use /newtask to create one!"
    
    await message.answer(response)
    logger.info(f"User {message.from_user.id} viewed their tasks")

async def process_kafka_messages():
    logger.info("Starting Kafka message processing thread")
    consumer = create_kafka_consumer()
    
    try:
        while True:
            try:
                for message in consumer:
                    try:
                        task_data = message.value
                        logger.info(f"Received task notification: {task_data}")
                        
                        user_id = task_data.get('user_id')
                        task_title = task_data.get('title')
                        due_date = task_data.get('due_date')
                        
                        if user_id and task_title and due_date:
                            message_text = (
                                f"🔔 Task Reminder\n\n"
                                f"Task: {task_title}\n"
                                f"Due Date: {due_date}\n\n"
                                f"This task is due soon!"
                            )
                            
                            try:
                                await bot.send_message(
                                    chat_id=user_id,
                                    text=message_text,
                                    parse_mode=ParseMode.HTML
                                )
                                NOTIFICATIONS_SENT.inc()
                                logger.info(f"Notification sent to user {user_id}")
                            except Exception as e:
                                logger.error(f"Failed to send notification to user {user_id}: {str(e)}")
                        else:
                            logger.warning(f"Invalid task data received: {task_data}")
                            
                    except Exception as e:
                        logger.error(f"Error processing Kafka message: {str(e)}")
                        continue
                        
            except Exception as e:
                logger.error(f"Kafka consumer error: {str(e)}")
                await asyncio.sleep(5)
                continue
                
    except asyncio.CancelledError:
        logger.info("Kafka message processing cancelled")
    finally:
        consumer.close()
        logger.info("Kafka consumer closed")

async def start_bot():
    logger.info("Starting Telegram bot...")
    # Start polling
    await dp.start_polling()
    logger.info("Telegram bot started successfully")

async def main():
    logger.info("Starting application...")
    
    # Start Kafka consumer in a separate task
    kafka_task = asyncio.create_task(process_kafka_messages())
    logger.info("Kafka consumer task created")
    
    # Start the bot
    await start_bot()
    
    # Wait for the Kafka task to complete (it shouldn't unless there's an error)
    await kafka_task

@kafka_broker.subscriber("task_due_soon")
async def handle_task_notification(body):
    try:
        logger.info(f"Received task notification: {body}")
        
        user_id = body.get('user_id')
        task_title = body.get('title')
        due_date = body.get('due_date')
        
        if user_id and task_title and due_date:
            message_text = (
                f"🔔 Task Reminder\n\n"
                f"Task: {task_title}\n"
                f"Due Date: {due_date}\n\n"
                f"This task is due soon!"
            )
            
            try:
                await bot.send_message(
                    chat_id=user_id,
                    text=message_text,
                    parse_mode=ParseMode.HTML
                )
                NOTIFICATIONS_SENT.inc()
                logger.info(f"Notification sent to user {user_id}")
            except Exception as e:
                logger.error(f"Failed to send notification to user {user_id}: {str(e)}")
        else:
            logger.warning(f"Invalid task data received: {body}")
            
    except Exception as e:
        logger.error(f"Error processing Kafka message: {str(e)}")

async def on_startup(dp):
    logger.info("Bot startup initiated")
    # Start Kafka broker
    await kafka_broker.start()
    logger.info("Kafka broker started")

async def on_shutdown(dp):
    logger.info("Bot shutdown initiated")
    # Stop Kafka broker
    await kafka_broker.close()
    await dp.storage.close()
    await dp.storage.wait_closed()
    logger.info("Bot shutdown completed")

if __name__ == '__main__':
    try:
        logger.info("Starting bot application")
        dp.run_polling(
            bot,
            on_startup=on_startup,
            on_shutdown=on_shutdown
        )
    except Exception as e:
        logger.error(f"Application error: {str(e)}")
    finally:
        logger.info("Application shutdown completed") 