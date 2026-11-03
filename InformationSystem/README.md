# Система моніторингу роботи БД

Лабораторна робота з дисципліни «Інформаційні системи».

Система збирає дані про роботу бази даних PostgreSQL і показує їх у **Grafana**:
- **метрики** збирає **Prometheus** і зберігає у своїй вбудованій TSDB;
- **логи** йдуть у **Grafana Loki**, **трейси** — у **Grafana Tempo**;
- доступ мають лише користувачі, що увійшли через власний **сервер авторизації (Python + SQLite)**.

Навантаження на БД створює курсовий проєкт **AnalyticsSystem** (ASP.NET Core + PostgreSQL) разом із Python-генератором відвідувачів сайту. Події між сервісами йдуть через **RabbitMQ**.

Що саме і як зроблено, описано в [docs/DETAILS.md](docs/DETAILS.md).

---

## 1. Що потрібно

| Що | Примітка |
|---|---|
| **Docker Desktop** (Windows / macOS) або Docker Engine + Compose v2 (Linux) | Інше встановлювати не треба: .NET, Python, PostgreSQL тощо працюють у контейнерах |
| Вільний порт **8080** | Інший порт можна задати в `.env`, див. розділ 7 |
| ~4 ГБ RAM для Docker і ~5 ГБ на диску | Стек має 15 контейнерів |
| Інтернет під час **першого** запуску | Docker завантажує образи, .NET- і Python-пакети |

## 2. Запуск

Перед запуском **Docker Desktop має бути відкритий і запущений.**

Отримати код (або розпакувати архів) і перейти в папку лабораторної:

```bash
git clone https://github.com/Roshira/University_Course4.git
cd University_Course4/InformationSystem
```

**Windows** — з папки проєкту в PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\run.ps1
```

Скрипт створить `.env` (якщо його немає), збере й запустить контейнери і відкриє браузер.

**Будь-яка ОС** — вручну:

```bash
cp .env.example .env
docker compose up -d --build
```

Перший запуск займає кілька хвилин, бо збираються образи .NET і Python. Наступні запуски тривають секунди.

Коли команда завершилась, **зачекайте ще ~1 хвилину**: сервіси підключаються одне до одного, а генератор накопичує перші дані. Поки цього не сталося, частина панелей може показувати «No data», це нормально.

Перевірити, що всі контейнери працюють:

```bash
docker compose ps
```

Має бути 15 рядків зі статусом `Up` (у `postgres` і `rabbitmq` ще `(healthy)`). `ingest-worker` запущений у двох екземплярах.

## 3. Вхід

Відкрийте **http://localhost:8080**. Система перенаправить на сторінку входу.

| Логін | Пароль |
|---|---|
| `admin` | `admin12345` |

Логін і пароль задаються в `.env` (`ADMIN_USERNAME`, `ADMIN_PASSWORD`).

Інші параметри `.env`:

| Змінна | Призначення |
|---|---|
| `AUTH_SECRET` | ключ підпису сесій. Якщо порожній, `auth-server` сам згенерує випадковий ключ і збереже його у volume `auth-data` |
| `GRAFANA_ADMIN_PASSWORD` | пароль вбудованого адміністратора Grafana. Увійти ним напряму не можна: вхід у Grafana лише через сервер авторизації |
| `GRAFANA_DB_PASSWORD` | пароль користувача PostgreSQL `grafana_ro` (лише читання), під яким працюють Grafana, `db-monitor` і `postgres-exporter` |
| `GENERATOR_SESSIONS_PER_SEC` | інтенсивність генератора навантаження |

Після входу відкриється дашборд **«Огляд системи»**. Інші дашборди відкриваються кнопкою **«Дашборди»** вгорі праворуч або через меню Grafana: *Dashboards → Моніторинг БД*.

| Адреса | Що там | Хто має доступ |
|---|---|---|
| http://localhost:8080/ | Grafana з 4 дашбордами | будь-який користувач після входу |
| http://localhost:8080/auth/users | керування користувачами, журнал входів | admin |
| http://localhost:8080/prometheus/ | Prometheus (Targets, Alerts, Graph) | admin |
| http://localhost:8080/rabbitmq/ | RabbitMQ Management, далі ще логін `telemetry` / `telemetry` | admin |
| http://localhost:8080/swagger | Swagger API курсової AnalyticsSystem (API працює в режимі Production, Swagger увімкнено окремим прапорцем `EnableSwagger`) | відкрито |
| http://localhost:8080/auth/logout | вихід | — |

## 4. Як перевірити, що все працює (≈5 хвилин)

1. **Огляд системи** (відкривається першим):
   - PostgreSQL = **UP**, Сервісів UP = **13**, Сервісів DOWN = **0**;
   - «Запис у БД» — приблизно 20–40 подій/с;
   - на графіку «Пропускна здатність конвеєра» три лінії йдуть разом: опубліковано → оброблено → записано в БД.
2. **PostgreSQL — робота СУБД**: розмір БД, з'єднання, TPS, cache hit ratio, операції з рядками, розміри таблиць і таблиця «Топ-10 запитів за сумарним часом» (`pg_stat_statements`).
3. **Аналітика сайту (дані з БД)**: топ кнопок, топ сторінок і воронка покупки. Нижні панелі читають дані **SQL-запитом напряму з PostgreSQL**.
4. **Логи і трейси**:
   - у полі «Пошук у тексті» введіть `Session published`;
   - розгорніть будь-який рядок і натисніть **«Відкрити трейс»** біля поля TraceID;
   - відкриється трейс у Tempo з повним шляхом події: `traffic-generator` → RabbitMQ → `ingest-worker` → `telemetry-api` → `telemetry.write` → SQL-запит у PostgreSQL.

   Нижче на цьому дашборді граф сервісів, побудований з трейсів.
5. **Prometheus**: http://localhost:8080/prometheus/targets — усі **13** цілей мають статус **UP**. На вкладці *Alerts* видно правила алертів.
6. **Авторизація і ролі**:
   - на http://localhost:8080/auth/users створіть користувача з роллю `viewer`;
   - вийдіть (`/auth/logout`) і увійдіть як він;
   - дашборди він бачить, а http://localhost:8080/prometheus/ — ні («Доступ заборонено»).

   Якщо 5 разів поспіль ввести неправильний пароль, вхід для цього логіна з цієї IP-адреси блокується на 5 хвилин. На дашборді «Огляд системи» видно невдалі входи.
7. **Відмовостійкість** (за бажанням):

   ```bash
   docker compose stop telemetry-api
   ```

   Через 30–60 с на графіку «Черги RabbitMQ» черга `telemetry.events` росте, а «Сервісів DOWN» стає 1. Тепер запустіть API знову:

   ```bash
   docker compose start telemetry-api
   ```

   Накопичені повідомлення обробляться за кілька секунд, черга впаде до нуля. Дані не втрачаються.

## 5. Автоматичні тести

Усі перевірки з розділу 4 (і ще багато інших) виконує скрипт. Потрібен лише Python 3.9+ без додаткових пакетів; стек має працювати щонайменше 2 хвилини.

```bash
python tests/integration_test.py
```

Параметри: `--base http://localhost:8081` (інший порт), `--user` і `--password` (інший адміністратор). На Windows, якщо в консолі «кракозябри», спочатку виконайте `set PYTHONIOENCODING=utf-8` (cmd) або `$env:PYTHONIOENCODING="utf-8"` (PowerShell).

Скрипт робить 86 перевірок і в кінці друкує `Пройдено: N, не пройдено: M`:
- **безпека:** редірект на вхід, підробка заголовка, CRLF-ін'єкція, відкритий редірект, CSRF, ролі admin/viewer, відкликання сесії, блокування після 5 невдалих входів;
- **Prometheus:** усі цілі `up`, правила алертів, немає критичних алертів, термін зберігання;
- **конвеєр даних:** події записуються в БД, швидкості публікації, обробки й запису збігаються, черги не ростуть, DLQ порожня;
- **БД:** `grafana_ro` не може змінювати дані й не бачить хешів паролів, у метриках немає секретів;
- **логи і трейси:** логи від усіх сервісів, нормалізовані рівні, наскрізний трейс від генератора до SQL, граф сервісів;
- **Grafana:** джерела даних, 4 дашборди, **кожна панель** повертає дані.

Тимчасовий користувач, якого створює тест, видаляється в кінці.

**Unit-тести** (сервер авторизації — 13, обробник черги — 7, курсова — 5):

```powershell
powershell -ExecutionPolicy Bypass -File .\tests\run_unit_tests.ps1
```

Python-тести виконуються всередині вже зібраних образів стека, тому Python локально не потрібен. Для C#-тестів потрібен .NET 10 SDK; якщо його немає, скрипт їх пропускає.

## 6. Зупинка

```bash
docker compose down        # зупинити, дані залишаються
docker compose down -v     # зупинити і видалити всі дані (БД, метрики, логи, користувачів)
```

## 7. Якщо щось не так

| Проблема | Що зробити |
|---|---|
| `port is already allocated` / 8080 зайнятий | У `.env` задайте `GATEWAY_PORT=8081` і запустіть `docker compose up -d` знову. Адреса стане http://localhost:8081 |
| `docker: command not found` або `Cannot connect to the Docker daemon` | Запустіть Docker Desktop і дочекайтеся статусу *Engine running* |
| Панелі показують «No data» | Зачекайте 1–2 хвилини після запуску. Перевірте `docker compose ps`: усі сервіси мають бути `Up` |
| Не підходить пароль адміністратора після зміни `.env` | Адміністратор створюється лише при першому запуску. Щоб застосувати новий пароль, видаліть дані: `docker compose down -v`, потім `docker compose up -d` |
| Змінили `GRAFANA_DB_PASSWORD` або `POSTGRES_*`, і Grafana / `db-monitor` не підключаються до БД | Init-скрипт PostgreSQL виконується лише на порожній БД. Або видаліть дані (`docker compose down -v`), або застосуйте скрипт повторно: `docker compose exec -T postgres sh /docker-entrypoint-initdb.d/10-init.sh` (у Git Bash додайте спереду `MSYS_NO_PATHCONV=1`) |
| Потрібна сторінка помилок ASP.NET з деталями | API навмисно запущено в режимі Production. Для налагодження задайте `ASPNETCORE_ENVIRONMENT: Development` у `docker-compose.yml` |
| Сервіс постійно перезапускається | Подивіться його лог: `docker compose logs --tail 100 <сервіс>`, наприклад `telemetry-api` |
| Мало пам'яті, контейнери падають | Docker Desktop → Settings → Resources: дайте Docker щонайменше 4 ГБ RAM |
| У Grafana → Connections → Tempo кнопка «Test» пише «Method not implemented» | Це нормально для Tempo в Grafana 11: перевірка зв'язку не реалізована, трейси при цьому працюють |

## 8. Структура проєкту

```
docker-compose.yml        увесь стек (15 контейнерів)
run.ps1                   запуск на Windows
.env.example              паролі та налаштування
TelemetrySystem.Api/      курсова AnalyticsSystem (ASP.NET Core) + метрики, трейси, JSON-логи
TelemetrySystem.Api.Tests/ unit-тести курсової
telemetry-dashboard/      фронтенд курсової (Angular), у стеку не запускається
services/
  workers/generator.py    генерація даних -> RabbitMQ
  workers/consumer.py     RabbitMQ -> API -> PostgreSQL
  workers/db_monitor.py   програмний моніторинг PostgreSQL (SQL до pg_stat_*)
  auth-server/app.py      сервер авторизації (FastAPI + SQLite)
  common/obs.py           спільні налаштування логів і трейсів для Python
  */tests/                unit-тести Python-сервісів
infra/                    конфігурації nginx, Prometheus, Loki, Tempo, Alloy, Grafana, PostgreSQL, RabbitMQ
tests/integration_test.py інтеграційний тест усього стека (86 перевірок)
tests/run_unit_tests.ps1  запуск усіх unit-тестів
docs/DETAILS.md           детальний опис роботи
```
