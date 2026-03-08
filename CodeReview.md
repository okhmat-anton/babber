# Code Review — AI Agents Server

> Дата: 2026-03-08 | Задача: AIS-55  
> Объём: Backend ~24,800 строк Python (110 файлов), Frontend ~16,900 строк Vue/JS (41 файл)

---

## Содержание

1. [Как упростить написание кода](#1-как-упростить-написание-кода)
2. [Как упростить код для нейросети](#2-как-упростить-код-для-нейросети)
3. [Как упростить сам код](#3-как-упростить-сам-код)
4. [Что лишнее и чего не хватает](#4-что-лишнее-и-чего-не-хватает)

---

## 1. Как упростить написание кода

### 1.1 Создать базовый класс `BaseMongoModel`

**Проблема:** Каждая из 15+ MongoDB-моделей повторяет один и тот же паттерн `to_mongo()` / `from_mongo()` — ручная конвертация `_id` ↔ `id`, datetime serialization. Суммарно **~600 строк** чистого boilerplate.

**Решение:** Один класс-миксин, который автоматически обрабатывает `_id` swap и сериализацию `datetime` полей через интроспекцию:

```python
class BaseMongoModel(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_mongo(self) -> dict:
        doc = self.model_dump()
        doc["_id"] = doc.pop("id")
        for key, value in doc.items():
            if isinstance(value, datetime):
                doc[key] = value.isoformat()
        return doc

    @classmethod
    def from_mongo(cls, doc: dict | None):
        if not doc:
            return None
        doc["id"] = doc.pop("_id", doc.get("id"))
        return cls(**doc)
```

**Результат:** Удаление ~600 строк дублирования. Новые модели создаются в 3 строки вместо 30.

### 1.2 Вынести утилиты фронтенда в общий модуль

**Проблема:** `formatBytes`, `statusColor`, `priorityColor`, `taskStatusColor`, `logLevelColor`, `scrollToBottom` — дублированы 3–5 раз в разных view.

**Решение:** Создать `frontend/src/utils/formatters.js` и `frontend/src/utils/colors.js`:

```js
// utils/formatters.js
export const formatBytes = (bytes) => { ... }
export const formatDate = (date) => { ... }

// utils/colors.js  
export const statusColor = (s) => ({ idle: 'grey', running: 'success' }[s] || 'grey')
export const priorityColor = (p) => ({ highest: 'red', high: 'orange' }[p] || 'grey')
```

**Результат:** Удаление ~150 строк дублей, единая точка изменений.

### 1.3 Centralized error handling в Pinia stores

**Проблема:** В stores `agents.js`, `tasks.js`, `skills.js`, `settings.js` — **40+ actions без try/catch**. Любая ошибка API уходит в unhandled promise rejection.

**Решение:** Обёртка `withErrorHandling`:

```js
function withErrorHandling(fn, errorMessage = 'Ошибка') {
  return async function (...args) {
    try {
      return await fn.apply(this, args)
    } catch (e) {
      console.error(errorMessage, e)
      throw e  // дать компоненту решить, что делать
    }
  }
}
```

Или перейти на Pinia plugin для глобальной обработки.

### 1.4 Вынести inline Pydantic-схемы в `app/schemas/`

**Проблема:** `chat.py` содержит ~8 определений Pydantic-схем прямо в файле API роутов. Аналогично `messengers.py`, `projects.py`, `ollama.py`.

**Решение:** Переместить в `app/schemas/chat.py`, `app/schemas/messenger.py` и т.д. Каталог `schemas/` уже существует, но используется не полностью.

### 1.5 Системные скилы — из строк в файлы

**Проблема:** `skill_service.py` содержит **500+ строк** Python-кода в виде строковых литералов (SYSTEM_SKILLS). Их невозможно линтить, тестировать или дебажить.

**Решение:** Хранить код скилов в `data/skills/<name>/code.py`, загружать при старте:

```python
SYSTEM_SKILLS = {}
for skill_dir in Path("data/skills").iterdir():
    code_file = skill_dir / "code.py"
    if code_file.exists():
        SYSTEM_SKILLS[skill_dir.name] = code_file.read_text()
```

---

## 2. Как упростить код для нейросети

> Ключевой принцип: нейросеть работает с ограниченным контекстным окном. Файлы >500 строк затрудняют понимание, а нетипичные паттерны вызывают галлюцинации.

### 2.1 Разбить файлы-монстры

| Файл | Строк | Рекомендация |
|------|-------|--------------|
| `frontend/src/views/AgentDetailView.vue` | **3,475** | Разбить на 14 tab-компонентов + 12 dialog-компонентов. Нейросети НЕ СПОСОБНА работать с файлом 3.5K строк целиком |
| `backend/app/services/staged_pipeline.py` | **2,076** | Разбить на: classification, stage runners, skill handlers, pipeline orchestrator |
| `backend/app/api/chat.py` | **1,775** | Разбить на: session CRUD, message sending, multi-model, search/summary |
| `frontend/src/components/ChatPanel.vue` | **1,615** | Разбить на: SessionList, MessageList, InputArea, MessageBubble, Settings |
| `backend/app/services/telegram_service.py` | **1,643** | Разбить на: auth flow, listener management, message handling |
| `frontend/src/views/ProjectDetailView.vue` | **1,337** | Вынести FileTree, ExecutionPanel, LogsPanel |
| `backend/app/services/agent_chat_engine.py` | **1,278** | Разбить: model resolution, context loading, prompt building, generation |
| `frontend/src/views/ModelsView.vue` | **1,132** | Вынести OllamaPanel, ModelCatalog, PullProgress, ChatTest |
| `backend/app/services/autonomous_runner.py` | **1,081** | Разбить: run management, cycle execution, code extraction |

**Правило:** Один файл ≤ 300 строк для Vue, ≤ 400 строк для Python. Нейросеть даёт значительно лучшие результаты на таком размере.

### 2.2 Убрать неоднозначные паттерны

**`send_message()` в chat.py — 400 строк в одной функции.** Это антипаттерн даже для людей. Для нейросети это один блок, который невозможно точечно модифицировать. Необходимо разбить на:
- `validate_session()`
- `save_user_message()`
- `build_context()`
- `call_llm()`
- `handle_protocol_response()`
- `save_assistant_message()`

**Deferred imports** (`from app.services.X import Y` внутри функций) — появляются 5+ раз. Нейросеть может не понять, что импорт доступен. Решить через рефакторинг зависимостей или facade-паттерн.

### 2.3 Исключить двойственность PostgreSQL/MongoDB

Наличие двух ORM слоёв (SQLAlchemy `app/models/` + Mongo `app/mongodb/`) путает нейросеть — она не знает, какой использовать. Удалить мёртвый PostgreSQL слой (см. §4.1).

### 2.4 Стандартизировать формат ответов API

Сейчас ошибки возвращают то `{"detail": "..."}`, то `{"message": "..."}`, то `MessageResponse(message="...")`. Нейросеть будет генерировать код с неправильным форматом. Стандартизировать на один формат.

### 2.5 Добавить docstrings и type hints

Большинство функций backend не имеют docstrings. Для крупных функций типа `generate_full()`, `_run_autonomous_loop()` — отсутствие документации делает невозможным для AI понять intent без чтения всего тела функции.

```python
async def generate_full(
    agent: MongoAgent,
    messages: list[dict],
    session_id: str,
    *,
    use_protocol: bool = True,
    max_tokens: int | None = None,
) -> LLMResponse:
    """Generate a complete response from agent's LLM.
    
    Builds system prompt, resolves model, loads context,
    and sends to LLM provider with streaming disabled.
    """
```

---

## 3. Как упростить сам код

### 3.1 Удалить мёртвый OllamaView.vue (~877 строк)

Роутер содержит `{ path: 'ollama', redirect: '/models' }`. OllamaView.vue **недоступен** через навигацию. Вся логика Ollama живёт в ModelsView.vue. Это **877 строк мёртвого кода**.

### 3.2 Удалить мёртвые SQLAlchemy модели (~800 строк)

Весь каталог `backend/app/models/` содержит SQLAlchemy ORM модели, которые **не используются** приложением (миграция на MongoDB завершена). Единственные ссылки — в `app/api/tasks.py` (который заменён на `tasks_mongo.py`) и в Alembic миграциях.

### 3.3 Удалить дублированную `MongoTask` модель

`MongoTask` определена дважды:
- `app/mongodb/models.py` (legacy, с UUID типами)
- `app/mongodb/models/task.py` (актуальная, string IDs)

Удалить `models.py`, оставить `models/task.py`.

### 3.4 Заменить `datetime.utcnow()` → `datetime.now(timezone.utc)`

**30+ вхождений** deprecated `datetime.utcnow()`. Начиная с Python 3.12 — выдаёт deprecation warning. Код уже частично использует `datetime.now(timezone.utc)` в API роутах, но модели — нет.

### 3.5 Консолидировать Ollama state management

Состояние Ollama отслеживается **в 4 независимых местах**: TopBar.vue, ModelsView.vue, OllamaView.vue, settingsStore. Они никогда не синхронизируются. Решение: единый `ollamaStore` или расширить `settingsStore`, а компоненты берут данные из него.

### 3.6 Логика пулла Ollama моделей дублирована

~80 строк SSE streaming кода для pull модели скопированы 1-в-1 между ModelsView.vue и OllamaView.vue. Вынести в composable `useOllamaPull()`.

### 3.7 Удалить дублированный `_TODO_STATUS_TO_TASK`

Маппинг статусов определён и в `autonomous_runner.py`, и в `todo_sync_service.py`. В `autonomous_runner.py` даже есть комментарий "moved to todo_sync_service.py", но код остался.

### 3.8 Inline FileTreeNode → отдельный компонент

`ProjectDetailView.vue` и `AgentDetailView.vue` определяют FileTreeNode как inline Options API компонент с template string. Это единственная причина, почему `vite.config.js` включает runtime compiler (**+14KB бандл**). Вынести в `FileTreeNode.vue` → удалить vue runtime compiler alias.

### 3.9 Store style: Options → Setup Function

Все 8 Pinia stores используют Options API, а все компоненты — Composition API `<script setup>`. Для consistent стиля перевести stores на `defineStore('name', () => { ... })`.

---

## 4. Что лишнее и чего не хватает

### 4.1 ЛИШНЕЕ

| Что | Где | Строк | Причина |
|-----|-----|-------|---------|
| SQLAlchemy модели | `backend/app/models/` | ~800 | Миграция на MongoDB завершена |
| `OllamaView.vue` | `frontend/src/views/` | 877 | Route делает redirect на ModelsView |
| `tasks.py` (PostgreSQL) | `backend/app/api/tasks.py` | 339 | Заменён на `tasks_mongo.py` |
| `models.py` (legacy Mongo) | `backend/app/mongodb/models.py` | ~120 | Заменён на `mongodb/models/` |
| `agents.py.bak` | `backend/app/api/` | ? | Бэкап файл в репозитории |
| Debug скрипты | корень проекта | ~200 | `check_log.py`, `check_logs.py`, `debug_chat.py`, `test_fixes.py`, `post_comment.py` |
| `console.log` в production | `stores/chat.js` | — | Отладочные логи |
| Runtime compiler alias | `vite.config.js` | — | Нужен только для inline template в FileTreeNode |
| Redirect роуты | `router/index.js` | — | `ollama → /models`, `settings/models → /models` |
| Дублирование `_TODO_STATUS_TO_TASK` | `autonomous_runner.py` | ~10 | Уже перенесён в `todo_sync_service.py` |
| SSL verify=False в `web_fetch` | `skill_service.py` | — | Уязвимость MITM |

### 4.2 НЕ ХВАТАЕТ

#### Безопасность (КРИТИЧНО)

| Что | Где | Риск |
|-----|-----|------|
| **Sandboxing для shell_exec** | Skill service | Полный доступ к системе через агента |
| **Path validation в file_read/file_write** | Skill service | Чтение `/etc/passwd`, запись куда угодно |
| **Нормальная KDF для шифрования** | `core/encryption.py` | Ключ = `JWT_SECRET * 2`[:32] — не PBKDF2/scrypt |
| **Rate limiting** | Все endpoint'ы | Нет ограничения на LLM вызовы |
| **Валидация длины сообщений** | `chat.py` | Можно отправить 10MB сообщение в LLM |
| **Фильтрация env variables** | `projects.py` | Можно выставить PATH, LD_PRELOAD |
| **Убрать pre-fill credentials** | `LoginView.vue` | admin/admin123 заполнены по умолчанию |

#### Производительность (ВЫСОКИЙ)

| Что | Где | Влияние |
|-----|-----|---------|
| **MongoDB индексы** | Все коллекции | Нет индексов на `session_id`, `agent_id`, `user_id`, `status` и др. — запросы деградируют с ростом данных |
| **N+1 в list_agents** | `agents.py` | 5-8 DB calls на каждого агента. 50 агентов = 250-400 запросов |
| **N+1 в get_project_chats** | `chat.py` | DB call на каждую сессию для загрузки сообщений |
| **API key O(n) bcrypt scan** | `dependencies.py` | Все ключи (до 1000) проверяются последовательно. Bcrypt ~100ms/ключ |
| **Virtual scrolling** | ChatPanel, AgentDetailView | Рендер ВСЕХ сообщений в DOM |
| **Vuetify tree-shaking** | `plugins/vuetify.js` | Импорт всех компонентов Vuetify, бандл unnecessarily large |

#### Архитектура (СРЕДНИЙ)

| Что | Где | Зачем |
|-----|-----|-------|
| **Error store / global error bus** | Frontend stores | Централизованная обработка ошибок |
| **Request deduplication** | Frontend API | Одинаковые запросы firing из разных компонентов |
| **Debounce на поисковых инпутах** | AgentErrorsView, SystemView | API calls на каждый keystroke |
| **Visibility-based polling** | TopBar.vue | 15-сек polling Ollama идёт даже когда вкладка не видна |
| **Pagination для chat messages** | Backend + Frontend | Грузятся все (до 10,000) сообщений сессии |
| **TypeScript** | Frontend | 16,900 строк без типов, ошибки ловятся только в runtime |
| **ARIA labels** | Все icon-only кнопки | Нулевая screen reader accessibility |

---

## Сводная таблица приоритетов

| # | Приоритет | Категория | Проблема | Эффект |
|---|-----------|-----------|----------|--------|
| 1 | **P0** | Безопасность | Shell exec без sandbox | Полный компромисс системы |
| 2 | **P0** | Безопасность | File skills без path validation | Произвольный доступ к ФС |
| 3 | **P0** | Безопасность | Слабая KDF для шифрования | Утечка credentials мессенджеров |
| 4 | **P1** | Мёртвый код | SQLAlchemy models + tasks.py + OllamaView | ~2,000 строк dead code |
| 5 | **P1** | Производительность | Нет MongoDB индексов | Деградация с ростом данных |
| 6 | **P1** | Производительность | N+1 queries (agents, chats) | 250-400 запросов на одну страницу |
| 7 | **P1** | Производительность | API Key O(n) bcrypt | 10 сек на авторизацию при 100 ключах |
| 8 | **P1** | Архитектура | AgentDetailView.vue 3,475 строк | Неподдерживаемый god-компонент |
| 9 | **P1** | Код | send_message() 400 строк | Нетестируемый, неподдерживаемый |
| 10 | **P2** | Код | BaseMongoModel boilerplate | ~600 строк дублей |
| 11 | **P2** | Код | Frontend утилиты дублированы | ~150 строк дублей |
| 12 | **P2** | Код | 30+ deprecated datetime.utcnow() | Python 3.12+ warnings |
| 13 | **P2** | Безопасность | Нет rate limiting | Abuse / cost risk |
| 14 | **P2** | UX | 40+ store actions без error handling | Unhandled promise rejections |
| 15 | **P2** | Производительность | Vuetify full import | Раздутый бандл |
| 16 | **P3** | Код | Inline schemas, hardcoded strings | Организация, i18n |
| 17 | **P3** | Код | 15+ silent exception swallowing | Скрытые ошибки в production |
| 18 | **P3** | UX | Нет ARIA labels | Нулевая accessibility |
