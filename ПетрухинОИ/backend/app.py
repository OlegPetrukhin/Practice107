import json
import logging
import os
import uuid

import redis
from flask import Flask, Response, jsonify, request
from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest

app = Flask(__name__)
app.logger.setLevel(logging.INFO)

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
TASK_QUEUE = os.getenv("TASK_QUEUE", "task_queue")

redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    decode_responses=True,
)

REQUESTS = Counter(
    "app_requests_total",
    "Total number of API requests received by the application",
)
TASKS_CREATED = Counter(
    "app_tasks_created_total",
    "Total number of analysis tasks created",
)


def task_key(task_id: str) -> str:
    return f"task:{task_id}"


@app.before_request
def count_api_request() -> None:
    if request.path.startswith("/api/"):
        REQUESTS.inc()


@app.get("/api/health")
def health():
    try:
        redis_client.ping()
        return jsonify({"status": "ok", "service": "backend"})
    except redis.RedisError as exc:
        app.logger.error("Healthcheck failed: %s", exc)
        return jsonify({"status": "error", "service": "backend"}), 503


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)


@app.post("/api/tasks")
def create_task():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Ожидается JSON-объект."}), 400

    text = data.get("text")
    if not isinstance(text, str):
        return jsonify({"error": "Поле text должно быть строкой."}), 400

    text = text.strip()
    if not text:
        return jsonify({"error": "Текст не должен быть пустым."}), 400
    if len(text) > 50000:
        return jsonify({"error": "Максимальная длина текста — 50000 символов."}), 400

    task_id = str(uuid.uuid4())
    payload = json.dumps({"task_id": task_id, "text": text}, ensure_ascii=False)

    try:
        redis_client.hset(
            task_key(task_id),
            mapping={"status": "queued", "result": "", "error": ""},
        )
        redis_client.expire(task_key(task_id), 3600)
        redis_client.rpush(TASK_QUEUE, payload)
        TASKS_CREATED.inc()
        app.logger.info("Task created: %s", task_id)
    except redis.RedisError as exc:
        app.logger.error("Cannot create task: %s", exc)
        return jsonify({"error": "Redis недоступен."}), 503

    return jsonify({"task_id": task_id, "status": "queued"}), 202


@app.get("/api/tasks/<task_id>")
def get_task(task_id: str):
    try:
        task = redis_client.hgetall(task_key(task_id))
    except redis.RedisError as exc:
        app.logger.error("Cannot read task %s: %s", task_id, exc)
        return jsonify({"error": "Redis недоступен."}), 503

    if not task:
        return jsonify({"error": "Задача не найдена."}), 404

    result = {
        "task_id": task_id,
        "status": task.get("status", "unknown"),
    }
    if task.get("result"):
        result["result"] = json.loads(task["result"])
    if task.get("error"):
        result["error"] = task["error"]

    return jsonify(result)
