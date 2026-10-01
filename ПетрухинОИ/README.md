Лабораторная работа №107 — Monitoring

Выполнил: Олег Петрухин

Цель

Изучить централизованный сбор логов и мониторинг микросервисного приложения.

Реализация

В работе используется приложение для анализа текста, состоящее из:

Frontend — веб-интерфейс;
Nginx — единая точка входа;
Backend — API и собственные метрики;
Redis — очередь задач;
Worker — обработка задач.

Для мониторинга используются Grafana Alloy, Mimir, Loki и Grafana.

Схема работы:


Browser
   |
Nginx :8080
   |------|
Frontend Backend
           |
         Redis
           |
         Worker

/metrics -> Alloy -> Mimir -> Grafana
logs     -> Alloy -> Loki  -> Grafana


Метрики и логи

Backend предоставляет:


http://localhost:8080/metrics


Основные метрики:


app_requests_total
app_tasks_created_total


Логи Backend и Worker собираются Alloy и передаются в Loki.

Grafana

Grafana автоматически подключает Mimir и Loki и загружает dashboard:


Laboratory 107 — Monitoring


На нём отображаются количество запросов, созданных задач и логи Backend.

Запуск

Требуется Docker Desktop с поддержкой WSL 2.

(Консоль)
docker compose config
docker compose up --build


Приложение:


http://localhost:8080


Grafana:


http://localhost:3000


Логин: admin
Пароль: admin

Проверка

(Консоль)
docker compose ps
curl http://localhost:8080/api/health
curl http://localhost:8080/metrics
docker compose logs backend


Для дополнительной проверки проекта:

(Консоль)
python tests/smoke_test.py


Результат

Создан локальный monitoring stack: метрики и логи собираются через Alloy, хранятся в Mimir и Loki и отображаются в Grafana на одном dashboard.
