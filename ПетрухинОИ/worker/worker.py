import json
import logging
import os
import re
import time
from collections import Counter

import redis

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
TASK_QUEUE = os.getenv("TASK_QUEUE", "task_queue")

redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    decode_responses=True,
)


def task_key(task_id: str) -> str:
    return f"task:{task_id}"


def analyze_text(text: str) -> dict:
    time.sleep(3)
    words = re.findall(r"[A-Za-zА-Яа-яЁё0-9]+", text.lower())
    counter = Counter(words)
    return {
        "characters": len(text),
        "words": len(words),
        "unique_words": len(counter),
        "top_words": counter.most_common(5),
    }


def process_task(payload: dict) -> None:
    task_id = payload["task_id"]
    key = task_key(task_id)
    redis_client.hset(key, mapping={"status": "processing", "error": ""})
    logging.info("Started task %s", task_id)

    try:
        result = analyze_text(payload["text"])
        redis_client.hset(
            key,
            mapping={
                "status": "completed",
                "result": json.dumps(result, ensure_ascii=False),
                "error": "",
            },
        )
        redis_client.expire(key, 3600)
        logging.info("Completed task %s", task_id)
    except Exception as exc:
        redis_client.hset(key, mapping={"status": "failed", "error": str(exc)})
        redis_client.expire(key, 3600)
        logging.exception("Task %s failed", task_id)


def main() -> None:
    logging.info("Worker started")
    while True:
        try:
            item = redis_client.blpop(TASK_QUEUE, timeout=5)
            if item is None:
                continue
            _, raw_payload = item
            process_task(json.loads(raw_payload))
        except redis.RedisError:
            logging.exception("Redis connection error")
            time.sleep(2)
        except json.JSONDecodeError:
            logging.exception("Invalid task payload")


if __name__ == "__main__":
    main()
