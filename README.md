# MJPEG Grid Viewer

FastAPI-приложение для просмотра, записи и стриминга снепшотов с IP-камер.
Минималистичный тёмный UI в духе Grok/xAI.

## Фичи

- Сетка камер на главной (`/`) — открыта, IntersectionObserver грузит ТОЛЬКО видимые тайлы (±200px), скрытые не дёргают апстрим.
- Запись на диск идёт независимо от вкладки и видимости — фоновые asyncio-таски на сервере.
- Edit Mode на главной — кнопка `edit` запрашивает пароль, тащишь тайлы, порядок мгновенно сохраняется.
- Админка (`/admin`) — Basic Auth, миниатюры камер у каждой строки.
- Дедупликация по URL: при добавлении (одиночном и bulk) дубликаты игнорируются. Кнопка `remove dups` чистит существующие.
- Авто-нумерация: имена `Camera N` пересчитываются после каждого add/delete (кастомные имена не трогаются). Кнопка `renumber` для ручного запуска.
- Глобальные настройки в админке: default FPS, tile size, IP url template — все в БД, применяются ко всем клиентам.
- Массовое добавление с галочкой `add as ip` (раскрытие IP по шаблону).
- Массовое удаление через чекбоксы (двухступенчатое подтверждение).
- Drag & Drop сортировка в админке и на главной.
- Запись MJPEG: 1ч / 100MB сегменты, `recordings/{cam_id}_{date}/`.
- Live MJPEG `/stream/{cam_id}` — играется в браузере и VLC.
- Авто-проверка камер каждые 10 минут: 3 неудачи подряд → `active=0`, при первом успехе → `active=1`.

## Структура

```
mjpeg-grid/
├── app/
│   ├── main.py
│   ├── db.py
│   ├── recorder.py
│   ├── health.py
│   ├── static/{app.js, admin.js, style.css}
│   └── templates/{index.html, admin.html, recordings.html}
├── data/                # SQLite (создаётся)
├── recordings/          # MJPEG записи (создаётся)
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── mjpeg-grid.service
└── README.md
```

## Деплой через Docker

```bash
unzip mjpeg-grid.zip && cd mjpeg-grid
sed -i 's/strongpassword123/MY_NEW_PASSWORD/' docker-compose.yml
docker compose up -d --build
```

Грид: `http://<VPS_IP>:8080/` · Админка: `http://<VPS_IP>:8080/admin`

## Деплой через systemd

```bash
sudo mkdir -p /opt/mjpeg-grid && sudo chown $USER /opt/mjpeg-grid
rsync -a ./ /opt/mjpeg-grid/
cd /opt/mjpeg-grid
python3 -m venv venv
venv/bin/pip install -r requirements.txt
venv/bin/pip install uvloop httptools
sudo cp mjpeg-grid.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now mjpeg-grid
journalctl -u mjpeg-grid -f
```

## Переменные окружения

| Переменная | По умолчанию | Описание |
|---|---|---|
| `ADMIN_LOGIN` | `admin` | Логин для `/admin` |
| `ADMIN_PASSWORD` | `strongpassword123` | Пароль для `/admin` |
| `SNAPSHOT_TIMEOUT` | `4.0` | Таймаут httpx (сек) |
| `MAX_CONCURRENT` | `32` | Семафор апстрим-запросов |
| `STREAM_FPS` | `5.0` | FPS для `/stream/{id}` |
| `REC_FPS` | `5.0` | FPS записи на диск |
| `REC_SEGMENT_BYTES` | `104857600` | Ротация записи по размеру |
| `REC_SEGMENT_SECONDS` | `3600` | Ротация записи по времени |
| `HEALTH_CHECK_INTERVAL` | `600` | Период автопроверки (сек) |
| `HEALTH_FAIL_THRESHOLD` | `3` | Неудач подряд → `active=0` |
| `IP_URL_TEMPLATE` | `http://{ip}/snapshot.cgi` | Дефолтный шаблон IP-режима (можно править в админке) |
| `DEFAULT_FPS` | `5.0` | Дефолтный FPS грида (можно править в админке) |
| `DEFAULT_TILE_SIZE` | `320` | Дефолтный размер тайла, px (можно править в админке) |

## Эндпоинты

| Метод | Путь | Auth | Описание |
|---|---|---|---|
| GET | `/` | — | Сетка |
| GET | `/snap/{id}` | — | Прокси-снепшот |
| GET | `/stream/{id}` | — | MJPEG поток |
| GET | `/admin` | Basic | Админка |
| GET | `/admin/whoami` | Basic | Пинг auth (Edit Mode) |
| POST | `/admin/add` | Basic | Добавить одну (с дедупом) |
| POST | `/admin/bulk_add` | Basic | Массовое добавление + as_ip + дедуп |
| POST | `/admin/delete/{id}` | Basic | Удалить одну |
| POST | `/admin/bulk_delete` | Basic | Удалить массово (JSON: ids) |
| POST | `/admin/dedupe` | Basic | Удалить все дубликаты по URL |
| POST | `/admin/renumber` | Basic | Пересчитать position и Camera N |
| POST | `/admin/update/{id}` | Basic | Обновить имя/url |
| POST | `/admin/active/{id}` | Basic | Включить/выключить |
| POST | `/admin/recording/{id}` | Basic | Запись on/off |
| POST | `/admin/probe/{id}` | Basic | Проверить одну |
| POST | `/admin/probe_all` | Basic | Проверить все |
| POST | `/admin/reorder` | Basic | Сохранить порядок |
| POST | `/admin/settings` | Basic | Настройки (fps, tile_size, ip_template) |
| GET | `/admin/recordings/{id}` | Basic | Список записей |
| GET | `/admin/recordings/{id}/file` | Basic | Скачать запись |

## Архитектура

- IntersectionObserver на фронте + `inflight`-флаг → видимые тайлы дёргают `/snap`, скрытые молчат.
- Запись (`RecorderManager`) — отдельный фоновый таск на каждую камеру с REC, не зависит от клиентов.
- `httpx.AsyncClient` + keep-alive + `asyncio.Semaphore(MAX_CONCURRENT)` ограничивает upstream.
- `HealthLoop` ходит на ВСЕ камеры (включая выключенные) и сам управляет `active`.
- SQLite + миграции через `PRAGMA table_info`. Глобальные настройки в `settings` (kv).
- Дедупликация по URL: при `bulk_add` фильтруется до запроса к камерам, при `dedupe` — оставляется первая по position.
- Renumber: position идёт 0..N-1, имена `Camera N` пересчитываются по индексу, кастомные имена не трогаются.
- Edit Mode на главной: Basic Auth кэшируется в `sessionStorage`, передаётся в Authorization при `/admin/reorder`.
