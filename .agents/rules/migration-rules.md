---
trigger: always_on
---

migration_flask_to_fastapi:
  goal: >
    Обеспечить безопасный и предсказуемый переезд существующего Flask‑сервиса на FastAPI
    с сохранением контрактов и поэтапным включением нового стека.

  principles:
    - backward_compatibility:
        description: >
          По умолчанию не ломать существующие HTTP‑контракты, если иное явно не разрешено.
        rules:
          - Сохранять пути, методы и форматы ответов, пока не согласованы breaking‑изменения.
          - При необходимости менять контракт — предлагать временный слой совместимости или параллельный endpoint (v2).
    - incremental_migration:
        description: >
          Переезд должен быть поэтапным, без “big bang” где возможно.
        rules:
          - Поощрять по‑модульную миграцию (blueprint → router) вместо переписывания всего сразу.
          - Предлагать временный режим dual‑run (Flask и FastAPI за общим proxy), если это допустимо.

  mapping_rules:
    flask_to_fastapi_concepts:
      - app:
          from: "Flask(app_name)"
          to: "FastAPI() с конфигурацией через settings."
      - blueprints:
          from: "Blueprint('users', __name__, url_prefix='/users')"
          to: "APIRouter(prefix='/users', tags=['users'])."
      - routes:
          from: "@app.route('/path', methods=['GET'])"
          to: "@router.get('/path') (или post/put/delete)."
      - request_data:
          from: "request.args, request.form, request.json"
          to: "Query/Body/Path параметры + Pydantic‑модели."
      - responses:
          from: "return jsonify(data), code"
          to: "return data (Pydantic‑модели/словарь) + status_code; response_model указывается в декораторе."
      - middlewares:
          from: "@app.before_request, @app.after_request"
          to: "middleware('http') и Depends для cross‑cutting logic."
      - globals:
          from: "g, current_app"
          to: "зависимости (Depends) и DI‑контейнер."

  code_practices:
    - Агент не переносит 1:1 императивный код из Flask‑view в FastAPI‑router; он выделяет:
        - схемы запросов/ответов (Pydantic),
        - сервисные функции,
        - репозитории/DAO для БД.
    - Flask‑специфичные конструкции (g, current_app, app.config, request.*) заменяются на:
        - dependency injection (Depends),
        - объект конфигурации (Pydantic Settings),
        - явные аргументы функций.

  async_strategy:
    - Если исходный Flask‑код синхронный и heavily завязан на sync‑клиенты/ORM:
        - Агент по умолчанию генерирует sync‑хендлеры (def, не async), чтобы не создавать скрытый blocking внутри event‑loop.
        - Переход на async‑стек выносится в отдельную фазу миграции.
    - Если есть уже async‑совместимые части (SQLAlchemy 2.x async, httpx, aio‑клиенты):
        - Агент может предлагать async‑эндпоинты, но обязан явно обозначать mix sync+async и риски блокировки.

  configuration_migration:
    - Конфиг:
        - Flask: app.config['KEY'], config.py модули.
        - FastAPI: Pydantic Settings + env‑переменные.
    - Агент:
        - Выносит конфиг в отдельный модуль core/config.py.
        - Переносит значения из Flask‑config в Pydantic‑модель, не хардкодя секреты.
        - Для чувствительных значений требует/предлагает переменные окружения.

  error_handling_and_logging:
    - Ошибки:
        - Flask: @app.errorhandler, abort().
        - FastAPI: HTTPException, кастомные exception_handlers.
    - Агент:
        - Мапит существующие коды и форматы ошибок на единый Error‑schema (Pydantic).
        - Сохраняет прежние коды и ключевые поля ошибок, если важна обратная совместимость.
    - Логи:
        - Если Flask‑код использует logging.getLogger / app.logger:
          агент сохраняет структуру логирования, но рекомендует/добавляет структурированные логи.

  security_migration:
    - Auth:
        - Flask‑login, самописные декораторы @login_required → Depends‑зависимости в FastAPI.
        - Существующие токен‑механизмы переносятся как есть, но агент предлагает миграцию на стандартные схемы (OAuth2/JWT) как отдельный этап.
    - Авторизация:
        - Декораторы вида @role_required → Depends‑функции, возвращающие текущего пользователя/роль и выбрасывающие HTTPException при отказе.
    - Сессии/куки:
        - Агент аккуратно переносит логику, сохраняя secure‑флаги, домены, сроки жизни куки.

  deployment_strategy:
    - Агент рекомендует:
        - Развести “как есть” Flask‑деплой и новый FastAPI‑деплой через общий reverse‑proxy.
        - На время миграции держать оба сервиса доступными для внутренних тестов (blue-green / canary).
        - Переход трафика делать поэтапно:
            - сначала внутренние клиенты/стейджинг,
            - потом процент прод‑трафика,
            - затем полное отключение Flask.
    - Конфигурация воркеров, timeout, keep‑alive и пр. параметров обговаривается явно; агент не меняет их без указаний.

  tests_and_verification:
    - Перед миграцией:
        - Агент поощряет добавление/усиление тестового покрытия Flask‑эндпоинтов (контракты, коды, структура JSON).
    - При переносе:
        - Тесты переносятся и адаптируются под FastAPI TestClient/httpx.
        - Добавляются regression‑тесты “Flask vs FastAPI”: ожидания по статус‑коду, структуре и ключевым полям.
    - После миграции:
        - Агент не предлагает удалить Flask‑код, пока:
            - тесты нового FastAPI‑сервиса зелёные,
            - ключевые сценарии проверены вручную/интеграционными тестами.

  anti_patterns:
    - Агент не должен:
        - переносить глобальное состояние Flask (g, singletons, ленивые импорты) в таком же виде.
        - смешивать Flask и FastAPI в одном процессе/приложении.
        - переписывать всё приложение целиком без возможности поэтапного rollback.
        - менять внешние API‑контракты “для красоты” без явного запроса.

  human_review:
    - Все критичные изменения (auth, billing, личные данные, массовые изменения схем БД) должны:
        - быть отмечены агентом как high‑risk,
        - оформляться отдельным MR/PR,
        - проходить обязательный human review.
