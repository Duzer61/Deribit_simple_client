# Deribit Price Tracker

Небольшой сервис-трекер index price: раз в минуту забирает `btc_usd` и `eth_usd`
из публичного API Deribit, складывает наблюдения в PostgreSQL и отдаёт их через
read-only HTTP API на FastAPI.

## Что умеет

- Периодический сбор index price `btc_usd` и `eth_usd` методом
  `public/get_index_price` — Celery Beat запускает задачу каждые 60 секунд.
- Сохранение наблюдения: тикер, точная цена (`Decimal` → `NUMERIC(30,12)`)
  и время наблюдения в секундах UNIX UTC.
- HTTP API только для чтения: все записи тикера, последняя сохранённая запись,
  записи за календарный день UTC.
- Разовый ручной сбор из CLI — тот же application-сценарий, что и у Celery-задачи.
- Контейнеризация: `postgres`, `redis`, разовое применение миграций, `api`, `worker`, `beat`.
- Точность цены не теряется: из JSON цена разбирается сразу в `Decimal`
  (`json.loads(..., parse_float=Decimal)`), в JSON-ответе отдаётся строкой.

## Стек

| Слой | Технологии |
|---|---|
| Runtime | Python 3.14.8 |
| HTTP API | FastAPI 0.143, Pydantic 2.14, pydantic-settings, Uvicorn 0.54 |
| Хранилище | PostgreSQL 17, SQLAlchemy 2.1 (async), asyncpg 0.32, Alembic 1.20 |
| Сбор | Celery 5.6 (+ redis transport), aiohttp 3.14 |
| Брокер | Redis 7 |
| Тесты и инструменты | pytest 9.1 + pytest-asyncio, HTTPX (ASGI transport), Ruff 0.17, mypy (strict) |
| Зависимости | `pyproject.toml` + `uv.lock`, менеджер — [uv](https://docs.astral.sh/uv/) |

## Архитектура и поток данных

```
Deribit public/get_index_price
        │  aiohttp: DeribitClient (повторные попытки только для временных ошибок)
        ▼
Celery Beat ──каждые 60 c──▶ Celery Worker
                                 │  asyncio.run → CollectPricesService.collect_once()
                                 │  на каждый тикер: HTTP-запрос → PriceObservation
                                 │  → отдельная короткая транзакция
                                 ▼
                          PostgreSQL: price_observations
                                 ▲
                                 │  SELECT (только чтение, к бирже не обращается)
                          FastAPI (read-only API)
```

Слои и направление зависимостей:

- `domain` — `Ticker`, `PriceObservation`, UTC-границы дня, доменные исключения.
  Не импортирует FastAPI, aiohttp, Celery, SQLAlchemy.
- `application` — сценарии (`CollectPricesService`, `PriceQueryService`) и порты
  (`Protocol`): `Clock`, `PriceSource`, `PriceRepository`, `PriceUnitOfWork`,
  `CollectionRunner`. Не знает конкретного HTTP-клиента и ORM.
- `infrastructure` — реализует порты: `DeribitClient`, `SqlAlchemyPriceRepository`,
  `SqlAlchemyPriceUnitOfWork`, фабрика Celery и задача сбора.
- `api` — HTTP-слой: маршруты, схемы, обработчики ошибок. Вызывает application,
  сам SQL и запросы к Deribit не выполняет.
- composition root — `bootstrap.py` (раннер сбора, Celery-приложение) и `lifespan`
  в `api/app.py` (engine и session factory).

```
src/deribit_tracker/
  domain/          models.py, exceptions.py
  application/     ports.py, services.py
  infrastructure/
    deribit/       client.py
    db/            models.py, repository.py, session.py
    celery/        factory.py, tasks.py, worker.py, beat.py
  api/             app.py, dependencies.py, routes.py, schemas.py, exception_handlers.py
  config.py        bootstrap.py        cli.py
alembic/versions/0001_create_price_observations.py
tests/unit/  tests/integration/
```


## Предварительные требования

- Python 3.14 и uv 0.9+ (проверено на Python 3.14.8 и uv 0.9.21).
- Docker с плагином Compose — для контейнерного запуска (проверено на Docker 29.9 и Compose 5.6).
- Свободные порты: `8000` (API), `55432` (PostgreSQL), `56379` (Redis).

## Быстрый запуск (Docker Compose)

```bash
cp .env.example .env      # демонстрационные значения; при необходимости измените
docker compose build
docker compose up -d
docker compose ps -a
```

Ожидаемое состояние: `api` — `Up (healthy)`, `migrate` — `Exited (0)`,
`worker` и `beat` — `Up`, `postgres` и `redis` — `Up (healthy)`.

Проверка работы и остановка:

```bash
docker compose exec -T api python -m deribit_tracker.cli collect-prices
curl 'http://127.0.0.1:8000/health'
curl 'http://127.0.0.1:8000/api/v1/prices/latest?ticker=eth_usd'
docker compose down       # данные PostgreSQL сохраняются в named volume postgres_data
```

Миграции применяет разовый сервис `migrate` (`alembic upgrade head`) до старта
`api`, `worker` и `beat`, поэтому вручную их запускать не нужно и они не выполняются
конкурентно несколькими процессами. Первую запись `beat` создаёт примерно через
60 секунд после старта.

## Локальный запуск без Docker

1. Инфраструктура в контейнерах, приложение — локально:

```bash
cp .env.example .env
docker compose up -d postgres redis
```

2. Зависимости и миграции:

```bash
uv sync
uv run alembic upgrade head
```

3. API (отдельный терминал):

```bash
uv run uvicorn deribit_tracker.api.app:create_app --factory --host 0.0.0.0 --port 8000
```

4. Worker и beat — в отдельных терминалах; beat запускается ровно один:

```bash
uv run python -m deribit_tracker.infrastructure.celery.worker
uv run python -m deribit_tracker.infrastructure.celery.beat
```

5. Ручной сбор, не дожидаясь beat:

```bash
uv run python -m deribit_tracker.cli collect-prices
```

## Переменные окружения

Полный список — в `.env.example`; реальные секреты в репозиторий не коммитятся,
файл `.env` добавлен в `.gitignore`. Значения из примера — локальные демонстрационные.

| Переменная | Назначение | Значение в `.env.example` |
|---|---|---|
| `DATABASE_URL` | подключение к PostgreSQL через asyncpg | `postgresql+asyncpg://deribit:deribit@localhost:55432/deribit_tracker` |
| `TEST_DATABASE_URL` | отдельная (не рабочая) база для integration-тестов | `postgresql+asyncpg://deribit:deribit@localhost:55432/deribit_tracker_test` |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | параметры контейнера PostgreSQL | `deribit` / `deribit` / `deribit_tracker` |
| `CELERY_BROKER_URL` | брокер Celery, схемы `redis://` или `rediss://` | `redis://localhost:56379/0` |
| `DERIBIT_BASE_URL` | базовый URL Deribit | `https://www.deribit.com/api/v2` |
| `HTTP_TIMEOUT_SECONDS` | таймаут HTTP-запроса | `10` |
| `HTTP_RETRY_ATTEMPTS` | максимум попыток запроса | `3` |
| `HTTP_RETRY_BACKOFF_SECONDS` | база экспоненциальной паузы между попытками | `0.5` |
| `HTTP_RETRY_MAX_AFTER_SECONDS` | верхняя граница ожидания по `Retry-After` | `5` |
| `COLLECT_INTERVAL_SECONDS` | период задачи beat | `60` |
| `LOG_LEVEL` | уровень логирования (`DEBUG`…`CRITICAL`) | `INFO` |

Обязательны только `DATABASE_URL` и `CELERY_BROKER_URL` — остальные имеют значения
по умолчанию. Все параметры валидируются при старте процесса; строки подключения
и секреты в логи не попадают. Внутри compose приложение обращается к `postgres:5432`
и `redis:6379`, наружу проброшен только `8000` (API), плюс loopback-порты
`127.0.0.1:55432`/`127.0.0.1:56379` для локальной разработки без Docker.

## Миграции

```bash
uv run alembic upgrade head   # применить миграции
uv run alembic current        # текущая ревизия: 0001 (head)
```

Строка подключения берётся из `DATABASE_URL` (`alembic/env.py` → `Settings`),
в `alembic.ini` она не дублируется. Схема создаётся миграцией, а не `metadata.create_all()`.

Таблица `price_observations`:

| Колонка | Тип | Ограничения |
|---|---|---|
| `id` | `BIGINT` | PRIMARY KEY, autoincrement |
| `ticker` | `VARCHAR(16)` | `CHECK ticker IN ('btc_usd','eth_usd')` |
| `price` | `NUMERIC(30,12)` | `CHECK price > 0` |
| `timestamp` | `BIGINT` | `CHECK timestamp >= 0` |

Индекс: `ix_price_observations_ticker_timestamp_id` по `(ticker, timestamp, id)`.


## API

Все три обязательных метода — `GET`, у каждого обязательный query-параметр `ticker`
со значениями `btc_usd` или `eth_usd` (только нижний регистр; `BTC`, `bitcoin` и прочие
алиасы не поддерживаются). `ticker` не является path-параметром, POST-методов нет.
Интерактивная схема: `/docs` (Swagger UI), машинная — `/openapi.json`.

| Метод | Путь | Назначение | Ответ |
|---|---|---|---|
| GET | `/api/v1/prices?ticker=btc_usd` | все сохранённые наблюдения тикера | `200`, массив (`[]`, если записей нет), порядок `timestamp ASC, id ASC` |
| GET | `/api/v1/prices/latest?ticker=btc_usd` | последнее сохранённое наблюдение | `200` — объект; `404`, если данных нет |
| GET | `/api/v1/prices/by-date?ticker=btc_usd&date=2026-10-14` | наблюдения за календарный день UTC | `200`, массив, `date` в формате `YYYY-MM-DD` |
| GET | `/health` | техническая проверка живости, в БД не ходит, `ticker` не нужен | `200` `{"status":"ok"}` |

Примеры (проверялись на живых данных проекта):

```bash
# все BTC-записи
curl 'http://127.0.0.1:8000/api/v1/prices?ticker=btc_usd'
# [{"id":1,"ticker":"btc_usd","price":"81127.090000000000","timestamp":1792053784}]

# последняя ETH-цена
curl 'http://127.0.0.1:8000/api/v1/prices/latest?ticker=eth_usd'
# {"id":8,"ticker":"eth_usd","price":"2372.860000000000","timestamp":1792055081}

# BTC-записи за указанный UTC-день
curl 'http://127.0.0.1:8000/api/v1/prices/by-date?ticker=btc_usd&date=2026-10-15'

# ticker отсутствует → 422
curl -i 'http://127.0.0.1:8000/api/v1/prices'

# неподдерживаемый ticker → 422
curl -i 'http://127.0.0.1:8000/api/v1/prices?ticker=btc'

# неверный формат даты → 422
curl -i 'http://127.0.0.1:8000/api/v1/prices/by-date?ticker=btc_usd&date=15-10-2026'

# технический healthcheck
curl 'http://127.0.0.1:8000/health'
# {"status":"ok"}
```

Ошибки: `422` — стандартная ошибка валидации FastAPI; `404` — `latest` при отсутствии
данных, например `{"detail":"no price observations stored for eth_usd"}`; `503` —
недоступность хранилища: `{"detail":"Price storage is temporarily unavailable"}`.
В HTTP-ответ не попадают SQL, строки подключения, пароли и traceback; внутренняя
ошибка логируется на сервере. «Последняя цена» — последняя **сохранённая** запись,
а не запрос к бирже в момент вызова.

## Формат ответа

```json
{
  "id": 8,
  "ticker": "eth_usd",
  "price": "2372.860000000000",
  "timestamp": 1792055081
}
```

| Поле | Тип JSON | Комментарий |
|---|---|---|
| `id` | integer | первичный ключ записи |
| `ticker` | string | `btc_usd` или `eth_usd` |
| `price` | string | десятичная строка; не JSON-число, чтобы не терять точность |
| `timestamp` | integer | секунды UNIX UTC |

`price` отдаётся строкой осознанно: JSON-число неизбежно проходит через двоичный
float и теряет точность `NUMERIC(30,12)`. Тип поля зафиксирован в OpenAPI описанием
`Index price as decimal string`.

## UTC и UNIX timestamp

- `timestamp` — момент получения **корректного** наблюдения клиентом, в секундах UNIX UTC.
  Это не плановое время запуска Celery, не дата записи, округлённая до минуты.
- Фильтр `by-date` трактует `date` как календарный день UTC:
  полуинтервал `[00:00:00 UTC этого дня; 00:00:00 UTC следующего дня)`.
  Запись ровно в начале дня включается, запись ровно в начале следующего дня — нет.
- Фильтрация выполняется сравнением `timestamp` с границами диапазона, а не функцией
  преобразования даты над каждой строкой, — такой запрос использует индекс.
- В качестве времени наблюдения **не используется** поле `usOut` (и другие служебные
  временные поля Deribit): это время формирования ответа биржей, а нам нужно время
  получения валидного наблюдения клиентом.

## Тесты и линтеры

```bash
uv run pytest tests/unit -q         # unit-тесты: без сети, БД и брокера → 96 passed
uv run pytest -m integration -q     # integration на реальном PostgreSQL → 8 passed
uv run ruff check .                 # All checks passed!
uv run ruff format --check .        # все файлы уже отформатированы
uv run mypy src tests               # Success: no issues found
```

Unit-тесты не обращаются к реальному Deribit и не требуют PostgreSQL: клиент
проверяется на локальном `aiohttp.test_utils.TestServer`, сервисы — на фейках.
Integration-тесты требуют переменной `TEST_DATABASE_URL` с отдельной базой
(см. `.env.example`); без неё они скипаются с пояснением. SQLite как замена
PostgreSQL не используется.


## Design decisions

**Почему `public/get_index_price`.** Задание требует «текущий index price валюты».
Именно этот метод отдаёт индексную цену валюты (`btc_usd`, `eth_usd`) и не требует
авторизации. Цены отдельных контрактов (last price, mark price, цена фьючерса,
`estimated_delivery_price`) не подходят: это не index price.

**Почему `btc_usd` и `eth_usd`.** Это допустимые значения `index_name` для
запрошенных заданием валют; в коде они закреплены `enum Ticker`, а в БД — CHECK-ограничением.
Единый регистр — нижний, алиасы не поддерживаются, чтобы не расширять контракт сверх задания.

**Почему публичному методу не нужны API-ключи.** `public/get_index_price` — публичный
метод: авторизация, приватные методы и API-ключи в задании явно исключены. Поэтому в сервисе
нет ни секретов биржи, ни OAuth-подписи.

**Почему цена хранится как `Decimal`/`NUMERIC(30,12)`.** `float` — двоичный формат,
он не может точно представить десятичные дроби, и накопление ошибок привело бы к
искажению цен. `NUMERIC` даёт точное десятичное значение, `Decimal` — точную арифметику
в Python. Диапазон `NUMERIC(30,12)` с большим запасом покрывает цены криптоактивов.

**Почему цена в JSON — строка.** JSON-число при разборе на клиенте всё равно становится
двоичным float, и точность теряется. Строка сохраняет значение байт-в-байт. Чтобы `Decimal`
не «пропустил» через float ещё при чтении ответа биржи, тело разбирается как
`json.loads(..., parse_float=Decimal)`.

**Почему timestamp — секунды UNIX UTC.** Задание требует именно UNIX timestamp.
UTC (а не локальное время) выбран, чтобы запись не зависела от таймзоны процесса и
сервера и чтобы фильтр по дате был однозначным. Время берётся через внедряемый объект
`Clock`, а не через `datetime.now()` внутри логики: иначе тесты зависели бы от реальных часов.
Служебные поля Deribit (`usOut` и прочие) как время наблюдения не используются.

**Почему дата фильтруется по UTC-дню.** Контракт `by-date` должен быть однозначным:
`date` — календарный день UTC, диапазон `[start; start + 1 день)`. Сравнение идёт по
`timestamp` с границами диапазона, поэтому используется индекс `(ticker, timestamp, id)`,
и функция даты не применяется к каждой строке. Границы вычисляет `utc_day_bounds`.

**Почему брокер — Redis.** Redis уже нужен окружению тестового задания и поддерживается
транспортом Celery «из коробки»; он прост в запуске (один контейнер, без кластера).
`result backend` не настраивается: результаты задач нигде не читаются (`task_ignore_result=True`).

**Почему Celery-задача синхронная, а клиент асинхронный.** Celery не умеет await-ить
корутины, и объявление задачи `async def` не сработало бы. Задача — обычная синхронная
функция, которая вызывает асинхронный сценарий через `asyncio.run`. Один `asyncio.run`
на один цикл сбора: внутри создаются aiohttp-сессия и async engine, а по завершении
оба освобождаются. Async engine не переиспользуется между разными event loop, потому что
каждый вызов `asyncio.run` создаёт свой loop. Повторные попытки выполняет только клиент
(не Celery и не клиент одновременно), не более трёх попыток и только для временных ошибок.

**Почему разделены api, worker и beat.** Это процессы с разным жизненным циклом и
разной нагрузкой: API — stateless read-only, worker масштабируется по нагрузке,
beat обязан быть в единственном экземпляре (иначе задачи дублировались бы).
Объединение их в один процесс смешало бы ресурсы (и потребовало бы общих глобальных
объектов) и усложнило бы диагностику.

**Почему нет глобальных экземпляров.** Ни `Settings`, ни `FastAPI`, ни `Celery`,
ни engine/session factory/`ClientSession` не создаются на уровне модуля. Всё создаётся
в точке входа и передаётся явно: зависимости FastAPI берутся из `app.state`, engine
закрывается в `lifespan`, раннер сбора владеет ресурсами через `async with`. Это даёт
предсказуемый жизненный цикл, отсутствие скрытого разделяемого состояния и тестируемость
без подмены модулей.

**Почему в endpoint «все данные» нет пагинации.** Задание требует вернуть все сохранённые
записи валюты, скрытый лимит исказил бы контракт. Пагинация — осознанно отложенное
улучшение (см. «Известные ограничения»).

**Как обработан частичный сбой двух запросов.** Тикеры собираются последовательно и
независимо: ошибка запроса по BTC не прерывает сбор ETH и наоборот. Сетевой запрос
выполняется **вне** транзакции БД, а каждое успешное наблюдение сохраняется своей
короткой транзакцией (`SqlAlchemyPriceUnitOfWork`: `commit` при успехе, `rollback` при
исключении, `close` всегда). Ошибка одного тикера не откатывает уже сохранённый второй.
Итог цикла — `CollectionReport(saved=..., failures=...)`, он же попадает в лог.

**Какие гарантии доставки реально обеспечиваются.** Транспорт Celery даёт
at-least-once: при повторной доставке задачи (ретрай брокера, рестарт worker до
подтверждения) возможны дубли наблюдений. Уникальность `(ticker, timestamp)` не
введена: timestamp имеет точность до секунды, и это удалило бы корректное наблюдение.
Детерминированный порядок при одинаковых timestamp обеспечивает сортировка `id`.
Exactly-once не гарантируется и не декларируется.


## Известные ограничения

- **Не exactly-once.** Доставка Celery — at-least-once, поэтому при повторной доставке
  задачи возможны дубли наблюдений (они не считаются ошибкой: это отдельные факты наблюдения).
- **API без авторизации.** Задание её не требует; сервис предназначен для локального
  запуска, а не для публичного интернета.
- **Нет пагинации** в `/api/v1/prices`: контракт требует «все записи», поэтому возвращается
  весь список. На больших объёмах это станет проблемой; пагинация — очевидное будущее улучшение.
- **Отклонение от optional-требования «два контейнера».** Реализовано шесть сервисов
  Compose: `api`, `worker`, `beat`, `migrate`, `postgres`, `redis`. Буквальный вариант
  «приложение + БД» не реализован: обязательный Celery требует брокера (`beat` и `worker` —
  независимые процессы с разным жизненным циклом), а `migrate` вынесен в разовую задачу,
  чтобы миграции не выполнялись конкурентно. Это осознанный компромисс, поскольку
  контейнеризация в задании опциональна. Утверждать, что шесть сервисов — это «два контейнера»,
  было бы неверно.
- **Ограничения тестового развёртывания.** Один worker с `concurrency=1`, один beat,
  без репликации и мониторинга; `restart: unless-stopped` есть, но отказоустойчивость
  не проверялась.
- **Документация `docs.deribit.com` была недоступна из окружения разработки** (network timeout).
  Контракт метода подтверждён live-запросами к публичному API: успешный ответ содержит
  `result.index_price` (например, BTC `81634.11`, ETH `2427.98`), неверный `index_name`
  даёт JSON-RPC ошибку `-32602` при HTTP 400. Ответы HTTP 429 и заголовок `Retry-After`
  на реальной бирже не наблюдались — соответствующая логика покрыта только unit-тестами
  с локальным тестовым сервером.
- **Работает только production public API.** Сервис не переключается на testnet неявно;
  для testnet нужно осознанно заменить `DERIBIT_BASE_URL`.

## Матрица выполнения требований

| Требование | Статус | Подтверждение |
|---|---|---|
| Контракт `public/get_index_price` проверен | частично | сама документация недоступна (timeout); контракт подтверждён live-запросами к публичному API |
| aiohttp-клиент получает index price обоих тикеров | выполнено | `tests/unit/test_deribit_client.py`; live-сбор `btc_usd` и `eth_usd` |
| Celery Beat запускает сбор каждые 60 с | выполнено | `COLLECT_SCHEDULE_SECONDS = 60.0` + лог beat: `Sending due task collect-prices-every-minute` через 60 c |
| Celery worker сохраняет наблюдения в PostgreSQL | выполнено | лог worker + строки в `price_observations` |
| Данные: тикер, точная цена, UNIX timestamp | выполнено | `NUMERIC(30,12)`, `BIGINT`; ответ API с `"price":"2372.860000000000"` |
| Три обязательных GET endpoint | выполнено | `/api/v1/prices`, `/api/v1/prices/latest`, `/api/v1/prices/by-date` |
| У каждого обязательного endpoint обязательный `ticker` | выполнено | `ticker: Ticker = Query(...)`; без параметра → 422 |
| Latest детерминированно выбирает последнюю запись | выполнено | `ORDER BY timestamp DESC, id DESC LIMIT 1`; integration-тест на одинаковых timestamp |
| Дата фильтруется по UTC-дню с верными границами | выполнено | `utc_day_bounds`; unit-тесты границ и integration-тест диапазона |
| Ошибки внешнего API и БД обработаны | выполнено | категории ошибок источника, `503` при недоступности, `404` для пустого latest |
| Нет глобальных экземпляров инфраструктуры | выполнено | `app.state` + `lifespan`, фабрики `create_app`/`create_celery_app`/`create_collect_runner` |
| Alembic-миграция | выполнено | `alembic/versions/0001_create_price_observations.py`; `alembic current` → `0001 (head)` |
| Unit-тесты по TDD проходят | выполнено | `uv run pytest tests/unit -q` → `96 passed` |
| Integration-тесты на PostgreSQL | выполнено | `uv run pytest -m integration -q` → `8 passed` |
| Линтинг и форматирование | выполнено | `ruff check .` → `All checks passed!`; `ruff format --check .` → без изменений |
| Docker-конфигурация проверена | выполнено | `docker compose config`, `build`, `up -d`, `ps -a` (api `healthy`, migrate `Exited (0)`), smoke в контейнере, `down` |
| README с Design decisions и реальными командами | выполнено | этот файл |
| Статус требования «два контейнера» указан честно | выполнено | раздел «Известные ограничения» |
| Репозиторий готов к GitHub | выполнено | `.gitignore`, `.dockerignore`, `.env.example`, отсутствие секретов в коммитах |
| Секреты не попали в коммит | выполнено | в репозитории только `.env.example` с демонстрационными значениями, `.env` в `.gitignore` |

## Публикация в GitHub

Push из этого окружения не выполнялся (нет явного разрешения и настроенного remote).
Чтобы опубликовать репозиторий самостоятельно:

```bash
# 1. Создайте пустой репозиторий на GitHub (без README, .gitignore и лицензии).

# 2. Проверьте, что секретов нет (в выводе не должно быть .env):
git status --short
git ls-files | grep -E '^\\.env(\\.|$)'

# 3. Подключите remote и отправьте ветку main:
git remote add origin git@github.com:<ваш-логин>/<ваш-репозиторий>.git
git push -u origin main
```

Если remote уже настроен, достаточно `git push -u origin main`.

## Полезные ссылки

- Swagger UI: `http://127.0.0.1:8000/docs`
- OpenAPI: `http://127.0.0.1:8000/openapi.json`
- Deribit API: <https://docs.deribit.com/>
- Использованный метод: <https://docs.deribit.com/#public-get_index_price>

