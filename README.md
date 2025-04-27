# Task Management System. Проект по архитектурам

A distributed task management system with deadline notifications, built as a Telegram bot.

## Architecture

The system consists of the following services:

- **Task Service**: Manages task storage and retrieval
- **Scheduler Service**: Monitors task deadlines and triggers notifications
- **Notifier Service**: Handles Telegram bot interactions and sends notifications
- **Redis**: Used for caching task data
- **Kafka**: Handles event-driven communication between services
- **Prometheus & Grafana**: Monitoring and visualization

## Prerequisites

- Docker
- Docker Compose
- Telegram Bot Token (required)

## Getting Started

1. Create a Telegram bot:
   - Message @BotFather on Telegram
   - Use `/newbot` command
   - Follow the instructions to create your bot
   - Save the bot token

2. Create a `.env` file in the root directory:
   ```
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token
   ```

3. Start the services:
   ```bash
   docker-compose up -d
   ```

4. Access the monitoring:
   - Grafana: http://localhost:3000
   - Prometheus: http://localhost:9090

## Using the Bot

1. Start a chat with your bot on Telegram
2. Use the following commands:
   - `/start` - Get started with the bot
   - `/create` - Create a new task
   - `/list` - List your tasks
   - `/delete` - Delete a task

### Creating a Task

When you create a task, send the information in this format:
```
Title
Description
Due Date (YYYY-MM-DD HH:MM)
```

Example:
```
Project Deadline
Complete the project documentation
2024-03-01 15:00
```

### Managing Tasks

- Use the keyboard buttons or commands to manage your tasks
- You'll receive notifications when tasks are due
- Each task has a unique ID that you can use to delete it

## Monitoring

The system includes comprehensive monitoring:

- Prometheus collects metrics from all services
- Grafana provides dashboards for visualizing:
  - Number of tasks created
  - Number of reminders sent
  - Bot command usage
  - Service health status

## Development

Each service is containerized and can be developed independently. The services communicate through:

- Event-driven messaging (Kafka)
- Caching (Redis)

## License

MIT 
