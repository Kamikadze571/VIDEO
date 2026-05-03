# MJPEG Grid Viewer

FastAPI-приложение для просмотра, записи и стриминга снепшотов с IP-камер.

## Фичи

- Сетка камер на главной (`/`) — открыта, ~5 FPS, IntersectionObserver, dblclick = fullscreen.
- **Edit Mode** на главной — кнопка `✎ Edit` запрашивает пароль, после чего тайлы перетаскиваются прямо в гриде, новый порядок мгновенно сохраняется в БД.
- Админка (`/admin`) — Basic Auth.
- **Массовое добавление** URL с авто-проверкой каждой камеры.
- **Режим IP**: галочка "Добавить как IP" — вставляешь только `192.168.1.10` или `192.168.1.10:8080`, шаблон URL применяется автоматически.
- **Массовое удаление** через чекбоксы (двухступенчатое подтверждение, без `confirm()`).
- **Drag & Drop** сортировка в админке и на главной.
- **Запись** на диск: 1 ч / 100 МБ сегменты в `recordings/{cam_id}_{date}/`.
- **Live MJPEG** `/stream/{cam_id}` — играется в браузере и VLC.
- **Авто-проверка** камер каждые 10 минут: 3 неудачи подряд → `active=0`, при первом успехе → `active=1`.
- Кнопка **Проверить все камеры** в админке.

## Структура

```
mjpeg-grid/
├── app/
│   ├── main.py              # FastAPI, эндпоинты, auth
│   ├── db.py                # SQLite + миграции + settings
│   ├── recorder.py          # фоновая запись
│   ├── health.py            # фоновая проверка камер
│   ├── static/{app.js, admin.js, style.css}
│   └── templates/{index.html, admin.html, recordings.html}
├── data/                    # SQLite (создаётся)
├── recordings/              # MJPEG записи (создаётся)
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── mjpeg-grid.service
└── README.md
```

## Деплой через Docker

```bash
git clone <repo> mjpeg-grid && cd mjpeg-grid
sed -i 's/strongpassword123/MY_NEW_PASSWORD/' docker-compose.yml
docker compose up -d --build
```

- Грид: `http://<VPS_IP>:8080/`
- Админка: `http://<VPS_IP>:8080/admin` → Basic Auth.

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
| `IP_URL_TEMPLATE` | `http://{ip}/snapshot.cgi` | Дефолтный шаблон IP-режима |

## Использование

### Edit Mode на главной
1. Жмёшь `✎ Edit` в шапке `/`.
2. Браузер запрашивает логин/пароль (один раз на сессию вкладки, кэш в `sessionStorage`).
3. Тащишь тайлы мышкой — порядок мгновенно летит в БД.
4. Жмёшь `✓ Done` — режим выключается.

### Массовое добавление по IP
В админке включаешь чекбокс **Добавить как IP**, в textarea вставляешь:
```
192.168.1.10
192.168.1.11:8080
192.168.1.12
```
Шаблон рядом (`http://{ip}/snapshot.cgi`) — поддерживает `{ip}` и опционально `{port}`. Сохраняется в БД при каждом успешном добавлении.

### Массовое удаление
Чекбоксы у каждой строки → появится панель `N выбрано` → `Удалить выбранные` → `Подтвердить удаление`. Подтверждение само сбрасывается через 5 сек.

### Авто-проверка
- Фоновый asyncio-таск ходит на каждую камеру (включая выключенные!) каждые `HEALTH_CHECK_INTERVAL` секунд.
- Успех → `fail_count=0`, `active=1` (камера вернётся в грид сама).
- Неудача → `fail_count++`. При достижении `HEALTH_FAIL_THRESHOLD` → `active=0`, камера пропадает из грида.
- Ручной toggle `active` сбрасывает `fail_count`.
- Кнопка **⟳ Проверить все** в админке делает то же синхронно.

### Live-стрим
Кнопка `Live` рядом с каждой камерой → `/stream/{id}`. В VLC: `Media → Open Network Stream → http://VPS:8080/stream/1`.

### Запись
Чекбокс REC. Файлы пишутся как `recordings/{cam_id}_{YYYY-MM-DD}/{HHMMSS}.mjpeg` с multipart-обёрткой.

Конвертация в mp4:
```bash
ffmpeg -i 143000.mjpeg -c:v libx264 -pix_fmt yuv420p out.mp4
```

## Эндпоинты

| Метод | Путь | Auth | Описание |
|---|---|---|---|
| GET | `/` | — | Сетка |
| GET | `/snap/{id}` | — | Прокси-снепшот |
| GET | `/stream/{id}` | — | MJPEG поток |
| GET | `/admin` | Basic | Админка |
| GET | `/admin/whoami` | Basic | Пинг auth (для Edit Mode) |
| POST | `/admin/add` | Basic | Добавить одну |
| POST | `/admin/bulk_add` | Basic | Массовое добавление (+ as_ip) |
| POST | `/admin/delete/{id}` | Basic | Удалить одну |
| POST | `/admin/bulk_delete` | Basic | Удалить массово (JSON: ids) |
| POST | `/admin/update/{id}` | Basic | Обновить имя/url |
| POST | `/admin/active/{id}` | Basic | Включить/выключить |
| POST | `/admin/recording/{id}` | Basic | Запись on/off |
| POST | `/admin/probe/{id}` | Basic | Проверить одну |
| POST | `/admin/probe_all` | Basic | Проверить все сразу |
| POST | `/admin/reorder` | Basic | Сохранить порядок |
| POST | `/admin/settings` | Basic | Обновить шаблон IP |
| GET | `/admin/recordings/{id}` | Basic | Список записей |
| GET | `/admin/recordings/{id}/file?name=...` | Basic | Скачать запись |

## Архитектура

- Один `setInterval(50ms)` на фронте + `inflight`-флаг + `IntersectionObserver` — нет лавины запросов.
- `httpx.AsyncClient` с keep-alive + `asyncio.Semaphore(MAX_CONCURRENT)` ограничивает upstream.
- `RecorderManager` синхронизирует фоновые таски с состоянием БД при каждом тоггле.
- `HealthLoop` — отдельный asyncio-таск, проверяет всё (включая выключенные) и сам управляет `active` через счётчик ошибок.
- SQLite + миграции через `PRAGMA table_info` — старая БД апгрейдится автоматом.
- Edit Mode на главной использует Basic Auth, креды кэшируются в `sessionStorage` и подкладываются в `Authorization` заголовок при `/admin/reorder`.

## Безопасность

Открыты только `/`, `/snap/{id}`, `/stream/{id}`. Все мутации, настройки, записи — за Basic Auth. Edit Mode на главной тоже требует пароль. Перед публикацией смени `ADMIN_PASSWORD`.
