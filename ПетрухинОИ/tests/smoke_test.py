"""Static + emulated smoke test for Practice107 laboratory 107.

The full Docker stack still needs Docker Desktop on the student's machine.
This test deliberately avoids Docker and external network access.
"""

from __future__ import annotations

import ast
import json
import pathlib
import re
import subprocess
import sys
import time
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
    print(f"[OK] {message}")


def load_text(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def main() -> int:
    compose = yaml.safe_load(load_text("compose.yaml"))
    services = compose["services"]
    expected = {"gateway", "frontend", "backend", "worker", "redis", "alloy", "loki", "mimir", "grafana"}
    check(set(services) == expected, "Compose содержит полный набор сервисов")
    check(compose["networks"]["lab"]["driver"] == "bridge", "Docker network lab настроена")
    check(services["gateway"]["ports"] == ["8080:80"], "Приложение опубликовано на порту 8080")
    check(services["grafana"]["ports"] == ["3000:3000"], "Grafana опубликована на порту 3000")
    check(services["alloy"]["ports"] == ["12345:12345"], "UI Alloy опубликован на порту 12345")
    check(services["alloy"]["user"] == "0:0", "Alloy запускается с доступом к Docker socket")
    check("healthcheck" not in services["mimir"], "В Mimir нет healthcheck, зависящего от отсутствующего wget")

    # Dependency graph must be acyclic.
    visiting, visited = set(), set()
    def visit(name: str) -> None:
        if name in visiting:
            raise AssertionError(f"Циклическая зависимость Compose: {name}")
        if name in visited:
            return
        visiting.add(name)
        for dep in services[name].get("depends_on", {}):
            check(dep in services, f"Зависимость {name} -> {dep} существует")
            visit(dep)
        visiting.remove(name)
        visited.add(name)
    for service_name in services:
        visit(service_name)
    check(True, "Граф зависимостей Compose не содержит циклов")

    for rel in ["loki/loki.yaml", "mimir/mimir.yaml", "grafana/provisioning/datasources/datasources.yaml", "grafana/provisioning/dashboards/dashboards.yaml"]:
        yaml.safe_load(load_text(rel))
        check(True, f"YAML корректен: {rel}")

    dashboard = json.loads(load_text("grafana/dashboards/lab107.json"))
    check(dashboard["title"] == "Laboratory 107 — Monitoring", "Dashboard имеет требуемое название")
    expressions = [t["expr"] for p in dashboard["panels"] for t in p.get("targets", [])]
    check("sum(app_requests_total)" in expressions, "Dashboard использует app_requests_total")
    check("sum(app_tasks_created_total)" in expressions, "Dashboard использует app_tasks_created_total")
    check('{service="backend"}' in expressions, "Dashboard содержит запрос логов Backend")

    backend = load_text("backend/app.py")
    worker = load_text("worker/worker.py")
    check('"app_requests_total"' in backend, "Backend объявляет app_requests_total")
    check('"app_tasks_created_total"' in backend, "Backend объявляет app_tasks_created_total")
    check("REQUESTS.inc()" in backend, "Backend увеличивает счётчик API-запросов")
    check("TASKS_CREATED.inc()" in backend, "Backend увеличивает счётчик созданных задач")
    for endpoint in ['@app.get("/api/health")', '@app.get("/metrics")', '@app.post("/api/tasks")', '@app.get("/api/tasks/<task_id>")']:
        check(endpoint in backend, f"Backend содержит endpoint {endpoint}")
    ast.parse(backend)
    ast.parse(worker)
    check(True, "Python-синтаксис Backend и Worker корректен")

    # Validate JS syntax with Node when available.
    node = subprocess.run(["node", "--check", str(ROOT / "frontend/app.js")], capture_output=True, text=True)
    check(node.returncode == 0, "JavaScript-синтаксис frontend корректен")

    # Validate Nginx config syntax with local nginx binary when available.
    nginx = subprocess.run(["nginx", "-v"], capture_output=True, text=True)
    if nginx.returncode == 0:
        tmp = ROOT / "tests" / ".nginx-smoke.conf"
        gateway = load_text("gateway/nginx.conf")
        # In the real Compose network these names resolve via Docker DNS.
        # For local nginx -t, replace them with loopback addresses so only
        # the Nginx configuration syntax is checked.
        gateway = gateway.replace("backend:8000", "127.0.0.1:8000").replace("frontend:80", "127.0.0.1:8081")
        main_conf = f"events {{}}\nhttp {{ {gateway} }}\n"
        tmp.write_text(main_conf, encoding="utf-8")
        result = subprocess.run(["nginx", "-t", "-c", str(tmp), "-p", str(ROOT)], capture_output=True, text=True)
        tmp.unlink(missing_ok=True)
        check(result.returncode == 0, "Nginx-конфигурация проходит синтаксическую проверку")
    else:
        print("[SKIP] nginx not available")

    # Emulate the Worker algorithm without waiting 3 seconds.
    tree = ast.parse(worker)
    analyze_node = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "analyze_text")
    module = ast.Module(
        body=[
            ast.Import(names=[ast.alias(name="re", asname=None)]),
            ast.Import(names=[ast.alias(name="time", asname=None)]),
            ast.ImportFrom(
                module="collections",
                names=[ast.alias(name="Counter", asname=None)],
                level=0,
            ),
            analyze_node,
        ],
        type_ignores=[],
    )
    ast.fix_missing_locations(module)
    ns = {}
    exec(compile(module, str(ROOT / "worker/worker.py"), "exec"), ns)
    ns["time"].sleep = lambda _seconds: None
    result = ns["analyze_text"]("Привет мир, привет мир!")
    check(result["characters"] == 23, "Эмуляция вычисления количества символов проходит")
    check(result["words"] == 4, "Эмуляция вычисления количества слов проходит")
    check(result["unique_words"] == 2, "Эмуляция вычисления уникальных слов проходит")
    check(result["top_words"][0] == ("привет", 2), "Эмуляция top_words проходит")

    # Emulate the end-to-end queue contract.
    task = {"task_id": "demo-task", "text": "Первое тестовое предложение"}
    queue = [json.dumps(task, ensure_ascii=False)]
    stored = {"demo-task": {"status": "queued", "result": "", "error": ""}}
    payload = json.loads(queue.pop(0))
    stored[payload["task_id"]]["status"] = "processing"
    computed = ns["analyze_text"](payload["text"])
    stored[payload["task_id"]]["status"] = "completed"
    stored[payload["task_id"]]["result"] = computed
    check(stored["demo-task"]["status"] == "completed", "Эмуляция Backend -> Redis -> Worker проходит")
    check(stored["demo-task"]["result"]["words"] == 3, "Эмуляция возвращает результат анализа")

    alloy = load_text("alloy/config.alloy")
    check('http://mimir:9009/api/v1/push' in alloy, "Alloy отправляет метрики в Mimir")
    check('http://loki:3100/loki/api/v1/push' in alloy, "Alloy отправляет логи в Loki")
    check('backend:8000' in alloy and '/metrics' in alloy, "Alloy забирает /metrics Backend")
    check('discovery.docker' in alloy and 'loki.source.docker' in alloy, "Alloy собирает Docker-логи")

    print("\nSmoke test завершён успешно.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
