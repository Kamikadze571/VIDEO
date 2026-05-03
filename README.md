# MJPEG Grid Viewer

FastAPI-приложение для просмотра, записи и стриминга снепшотов с IP-камер.
Минималистичный тёмный UI в духе Grok/xAI. Полностью русифицирован.

## Фичи

- **Вкладки**: камеры группируются по именованным вкладкам ("Улица", "Дом", "Склад"...). Перетаскиванием камера переезжает между вкладками. По умолчанию — одна вкладка "Все камеры".
- **Сетка камер на главной** (`/`): открыта, IntersectionObserver грузит ТОЛЬКО видимые тайлы (±200px), скрытые не дёргают апстрим.
- **Запись на диск** идёт независимо от вкладки и видимости — фоновые asyncio-таски на сервере.
- **Edit Mode** на главной: кнопка `правка` запрашивает пароль, тащишь тайлы внутри вкладки или на другую вкладку для перемещения, можно создать новую вкладку.
- **Админка** (`/admin`): Basic Auth, миниатюры камер, управление вкладками (создание/переименование/удаление).
- **Дедупликация по URL**: при добавлении дубликаты пропускаются. Кнопка `Удалить дубли` чистит существующие.
- **Авто-нумерация**: имена `Камера N` сквозные по всем вкладкам, пересчитываются после изменений. Кастомные имена не трогаются.
- **Глобальные настройки** в админке: FPS, размер тайла, шаблон IP-URL.
- **Массовое добавление** с режимом IP (раскрытие шаблона по `{ip}`/`{port}`).
- **Массовое удаление** через чекбоксы (двухступенчатое подтверждение).
- **Drag & Drop** сортировка в админке и на главной.
- **Live MJPEG** `/stream/{cam_id}` — играется в браузере и VLC.
- **Авто-проверка** камер каждые 10 минут: 3 неудачи подряд → `active=0`, при первом успехе → `active=1`.

## Деплой через Docker

```bash
unzip mjpeg-grid.zip && cd mjpeg-grid
sed -i 's/strongpassword123/MY_NEW_PASSWORD/' docker-compose.yml
docker compose up -d --build
```

Грид: `http://<VPS_IP>:8080/` · Админка: `http://<VPS_IP>:8080/admin`

## Структура

```
mjpeg-grid/
├── app/
│   ├── main.py
│   ├── db.py            # tabs + cameras + settings + миграции
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
| `IP_URL_TEMPLATE` | `http://{ip}/snapshot.cgi` | Дефолтный шаблон IP |
| `DEFAULT_FPS` | `5.0` | Дефолтный FPS грида |
| `DEFAULT_TILE_SIZE` | `320` | Дефолтный размер тайла, px |

## Использование вкладок

- В админке вкладки в шапке. Клик по вкладке — переключение, кнопки `✎` и `×` рядом — переименовать/удалить (двойное нажатие на `×` подтверждает удаление). При удалении вкладки её камеры переезжают в первую оставшуюся.
- Чтобы переместить камеру в другую вкладку — тащи строку таблицы (или тайл на главной в режиме `правка`) на нужную вкладку сверху.
- Кнопка `+ новая вкладка` создаёт вкладку с заданным именем.
- Адресуется через `?tab=N`. Без параметра показывается первая вкладка.

## Эндпоинты

| Метод | Путь | Auth |
|---|---|---|
| GET | `/?tab=N` | — |
| GET | `/api/cameras?tab=N` | — |
| GET | `/api/tabs` | — |
| GET | `/snap/{id}` | — |
| GET | `/stream/{id}` | — |
| GET | `/admin?tab=N` | Basic |
| GET | `/admin/whoami` | Basic |
| POST | `/admin/tabs/add` | Basic |
| POST | `/admin/tabs/rename/{id}` | Basic |
| POST | `/admin/tabs/delete/{id}` | Basic |
| POST | `/admin/tabs/reorder` | Basic |
| POST | `/admin/cameras/{id}/move` | Basic |
| POST | `/admin/add` | Basic |
| POST | `/admin/bulk_add` | Basic |
| POST | `/admin/delete/{id}` | Basic |
| POST | `/admin/bulk_delete` | Basic |
| POST | `/admin/dedupe` | Basic |
| POST | `/admin/renumber` | Basic |
| POST | `/admin/update/{id}` | Basic |
| POST | `/admin/active/{id}` | Basic |
| POST | `/admin/recording/{id}` | Basic |
| POST | `/admin/probe/{id}` | Basic |
| POST | `/admin/probe_all` | Basic |
| POST | `/admin/reorder` | Basic |
| POST | `/admin/settings` | Basic |
| GET | `/admin/recordings/{id}` | Basic |
| GET | `/admin/recordings/{id}/file` | Basic |
