"""Redis连接"""
import redis
from app.core.config import settings

redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True,
                              socket_timeout=30, socket_connect_timeout=10)

# Stream names
TASK_STREAM = "tasks:stream"
AGENT_COMMAND_STREAM = "agent:commands"
EVENT_STREAM = "events:stream"

# Queue groups
TASK_WORKER_GROUP = "task-workers"
STATIC_WORKER_GROUP = "static-workers"
