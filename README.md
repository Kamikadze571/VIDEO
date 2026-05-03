# MJPEG Grid Viewer

FastAPI-приложение для просмотра, записи и стриминга снепшотов с IP-камер.

## Фичи

- Сетка камер на главной (`/`) — open access, ~5 FPS, IntersectionObserver, двойной клик = fullscreen.
- Админка (`/admin`) — Basic Auth.
- Массовое добавление URL с авто-проверкой (рабочие → активные, нерабочие → неактивные).
- Drag & Drop сортировка (порядок в БД).
- Включение записи на камеру → MJPEG-файлы по 1 ч / 100 МБ в `./recordings/{cam_id}_{date}/`.
- Live MJPEG-стрим `/stream/{cam_id}` (`multipart/x-mixed-replace`) — открывается прямо в браузере или в VLC.
- Прокси `/snap/{cam_id}` решает CORS, хранит keep-alive к камерам.

## Структура

```
mjpeg-grid/
├── app/
│   ├── main.py
│   ├── db.py
│   ├── recorder.py
│   ├── static/{app.js, admin.js, style.css}
│   └── templates/{index.html, admin.html, recordings.html}
├── data/                # SQLite (создаётся автоматом)
├── recordings/          # MJPEG записи (создаётся автоматом)
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── mjpeg-grid.service
└── README.md
```

## Деплой через Docker

```bash
git clone <repo> mjpeg-grid && cd mjpeg-grid

# смени пароль админки
sed -i 's/strongpassword123/MY_NEW_PASSWORD/' docker-compose.yml

docker compose up -d --build
```

- Грид: `http://<VPS_IP>:8080/`
- Админка: `http://<VPS_IP>:8080/admin` → Basic Auth (`admin` / пароль из `ADMIN_PASSWORD`)

## Деплой через systemd

```bash
sudo mkdir -p /opt/mjpeg-grid && sudo chown $USER /opt/mjpeg-grid
rsync -a ./ /opt/mjpeg-grid/
cd /opt/mjpeg-grid
python3 -m venv venv
venv/bin/pip install -r requirements.txt
venv/bin/pip install uvloop httptools

# отредактируй пароль в unit-файле
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
| `REC_SEGMENT_BYTES` | `104857600` | Ротация по размеру (байт) |
| `REC_SEGMENT_SECONDS` | `3600` | Ротация по времени (сек) |

## Firewall

```bash
sudo ufw allow 8080/tcp
```

## Использование

### Массовое добавление
В админке — textarea, по одной ссылке на строку, кнопка **Добавить все**. Проверка идёт параллельно. Нерабочие подсвечиваются красным и не отображаются на главной.

### Live-стрим
Кнопка `Live` рядом с каждой камерой (в админке и в гриде) открывает `/stream/{id}` — непрерывный MJPEG. Можно открыть в VLC: `Media → Open Network Stream → http://VPS:8080/stream/1`.

### Запись
Чекбокс REC в админке — мгновенно поднимает фоновый воркер `CameraRecorder` (asyncio task на httpx). Файлы пишутся как `recordings/{cam_id}_{YYYY-MM-DD}/{HHMMSS}.mjpeg` с multipart-обёрткой (совместимы с VLC и ffmpeg).

Конвертация в mp4:
```bash
ffmpeg -i 143000.mjpeg -c:v libx264 -pix_fmt yuv420p out.mp4
```

### Эндпоинты

| Метод | Путь | Auth | Описание |
|---|---|---|---|
| GET | `/` | — | Сетка |
| GET | `/snap/{id}` | — | Прокси-снепшот |
| GET | `/stream/{id}` | — | MJPEG поток |
| GET | `/admin` | Basic | Админка |
| POST | `/admin/add` | Basic | Добавить одну |
| POST | `/admin/bulk_add` | Basic | Массовое добавление |
| POST | `/admin/delete/{id}` | Basic | Удалить |
| POST | `/admin/update/{id}` | Basic | Обновить имя/url |
| POST | `/admin/active/{id}` | Basic | Включить/выключить |
| POST | `/admin/recording/{id}` | Basic | Запись on/off |
| POST | `/admin/probe/{id}` | Basic | Проверить камеру |
| POST | `/admin/reorder` | Basic | Сохранить порядок |
| GET | `/admin/recordings/{id}` | Basic | Список записей |
| GET | `/admin/recordings/{id}/file?name=...` | Basic | Скачать запись |

## Архитектура

- Один `setInterval(50ms)` на фронте дёргает только видимые тайлы — без 100500 таймеров.
- `inflight`-флаг на тайле: новый запрос не уйдёт пока не вернулся прошлый.
- `IntersectionObserver` отключает невидимые камеры.
- `httpx.AsyncClient` + keep-alive + `asyncio.Semaphore(MAX_CONCURRENT)` ограничивает нагрузку на апстрим.
- `RecorderManager` синхронизирует фоновые задачи записи с состоянием БД на каждое изменение чекбокса.
- SQLite + миграции по `PRAGMA table_info` — апгрейд старой БД работает автоматом.

## Безопасность

Открытым остаётся только `/`, `/snap/{id}`, `/stream/{id}`. Все мутирующие эндпоинты и просмотр записей — за Basic Auth. Перед публикацией поменяй `ADMIN_PASSWORD`.
