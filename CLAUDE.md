# Oswin (бывший J.A.R.V.I.S., затем Sayro) — голосовой ИИ-ассистент для Windows

Продукт Арсения для рынков США и ЕС (бесплатно + Pro $4.99/мес). Общение с Арсением — на русском; интерфейс продукта — 10 языков. Ноутбук: Windows 11, RTX 5070 Laptop, экран 2560×1600,
гарнитура Razer BlackShark V3 Pro. Город по умолчанию — Жилина (Словакия).

## Как устроено

- **Бренд — только `core/brand.py`** (Oswin с 3.1; имя выбрано после проверки торговых марок в TMview: Sayro занят другим голосовым приложением в Microsoft Store, JARVIS — марка Marvel в классе 9 именно на голосового ассистента). Старые названия окон/ярлыков — `LEGACY_TITLES`/`LEGACY_NAMES`, миграция ярлыков в `jarvis.py`. (NAME, локализованные имена, варианты распознавания имени для активации). Заголовок окна
  всегда `WINDOW_TITLE` — по нему ядро ищет окно (не локализовать). Ключ `/ping` → `{"jarvis": true}` не менять: его проверяют старые установщики.
- **Переводы**: английский источник — тексты в `ui/index.html` (`data-i18n`, `data-i18n-ph`, `data-i18n-title`), `STR` в `ui/app.js`,
  `PY`/`PY_ONLY` в `core/i18n.py` (сообщения ядра пишутся по-русски и переводятся по шаблону в `Assistant.toast`).
  `python tools/build_i18n.py` → `ui/i18n/en.json`; на ноутбуке `selftest.py --only i18n` (= `tools/translate_i18n.py`)
  переводит недостающие ключи через Gemini во все `ui/i18n/<lang>.json`. После изменения текстов — оба шага.
- Системный промпт модели — на английском (`build_prompt`), модель отвечает на языке пользователя.
- Пробный период: `data/trial.json` (7 дней Pro с первого запуска), `License.pro = licensed or trial`.

- `jarvis.py` — точка входа (проверка второй копии через `/ping`, DPI awareness, удаление dev-мусора).
- `core/assistant.py` — оркестратор: слово активации → Live-сессия → инструменты → UI. Тут же системный промпт (`build_prompt`,
  CHARACTER/LENGTH/LANG) и обработчик команд из интерфейса (`handle_ui`, `apply_settings`).
- `core/live.py` — сырой клиент Gemini Live API через `aiohttp` websocket (без google-genai/pydantic).
- `core/gemini.py` — REST: список моделей, текст, зрение, TTS, `search()` (Google через Edge → выжимка моделью).
- `core/tools.py` — все инструменты (~47, включая режимы `routine_*`, `quiet_mode`, `watch_screen`, `game_clip`, `discord`). Описания в `_declarations()`, реализация `t_<name>`. Группы для отключения — `TOOL_GROUPS` в config.
- `core/apps.py` — индекс программ (меню «Пуск» + `Get-StartApps`), русские алиасы, поиск файлов.
- `core/winsys.py` — Windows через ctypes: клавиши, мышь, громкость (pycaw), яркость (WMI), буфер обмена, окна, питание, статистика.
- `core/audio.py` — микрофон 16 кГц / динамик 24 кГц (sounddevice, MME), чимы, автоопределение гарнитуры.
- `core/wake.py` — активация. «Hey Oswin»: распознавание коротких фраз Google STT на языке интерфейса (+ второй шанс на en-US), т.к. локальной модели пока нет. «Hey Jarvis» (`wake_word=jarvis`): openWakeWord + проверка речью. TODO: обучить openWakeWord `hey_oswin` (приватность для ЕС, точность).
- `core/websearch.py` — Google через `msedge --headless --dump-dom`, Google News RSS, Википедия, первое видео YouTube.
- `core/server.py` — aiohttp на 127.0.0.1:8765 (UI + `/ws`), `core/desktop.py` — окно (WebView2 через `core/window.py` — отдельный процесс pywebview; запасной вариант Edge `--app`, `window_engine` в config), трей, хоткей, автозапуск, рестарт.
- **Оболочка `Oswin.exe` (папка `shell/`, Rust: wry + tao, ~1 МБ)** — главный процесс в версии из установщика: одна копия (мьютекс `Local\\OswinHost`, вторая копия делает POST `/show` и выходит), ядро `pythonw jarvis.py` — дочерний процесс с `OSWIN_HOST_TOKEN`, окно WebView2 «Oswin» (данные — `data/webview`), лог `data/host.log`. Связь — `core/host.py`: ядро пишет `data/host.json` (port, token), команды окну — долгий опрос `GET /host/next`. Коды выхода ядра: 0 — выход (или обновление: `update_helper` сам запускает `Oswin.exe`), 3 — перезапуск, иное — сбой (≤3 перезапусков за 2 мин). Без оболочки (`host.ACTIVE=False`) всё как раньше: `core/window.py`. Собирается в `installer.yml` (`cargo build`), проверка — `installer/test_host.py` (окно, вторая копия, перезапуск, выход). Обновления через `updater` Oswin.exe НЕ меняют — только новый установщик.
- `core/telegram.py` — Telegram-бот (long polling, без сервера): привязка по 6-значному коду, текстовый агент Gemini REST +
  те же инструменты (цикл functionCall → functionResponse, части модели возвращаются как есть ради thoughtSignature), голосовые/фото, `/screen`, `/status`.
- Проактивность — `Assistant._proactive_loop` (раз в 20 с по `last_stats`): перегрев ГП, батарея, диск, долгая игра (игра = средняя загрузка ГП ≥45% за 3 мин),
  ночь. `announce()` → тост + Telegram, голосом через `[СИСТЕМА: …]` в Live, если не тихий режим (`store.quiet_until`).
- Утренний брифинг — блок в системном промпте (`_briefing_block`) при первой сессии дня с 5 до 12 (`store.last_briefing`).
- «Вижу экран» — `set_watch()` + `_watch_loop`: JPEG 1280 px каждые `watch_interval` с через `realtimeInput.video`; idle-таймаут `watch_idle_timeout`.
- Обновления — `core/updater.py` (`VERSION`/`CHANGELOG.md` из ветки `main` репозитория `update_repo` через raw.githubusercontent, zip через codeload, проверка раз в 6 ч) + `core/update_helper.py` (отдельный процесс из
  `data/update/helper.py`: ждёт выхода, копия в `data/backup/v<old>`, ставит файлы, pip при новом requirements.txt, ждёт `/ping` 60 с, иначе откат).
  Результат — `data/update/result.json`, его показывает новая версия при старте. Версия — файл `VERSION`.
- `ui/` — интерфейс в стиле Apple (index.html, style.css, app.js, i18n.js): шар, «Сегодня», флаги, настройки-лист с 14 разделами, мастер первого запуска (`#onb`), темы light/dark/system.
- `core/config.py` — DEFAULTS + SCHEMA/`coerce()` (всё, что меняется из UI, проходит через coerce).
- Данные: `config.json` (там API-ключ и токен Telegram!), `data/data.json` (таймеры, задачи, заметки, память, история, режимы, тихий режим), `jarvis.log`.

## Запуск и проверка

```bat
.venv\Scripts\python.exe jarvis.py --console      :: с логом в консоли (или start_debug.bat)
.venv\Scripts\python.exe selftest.py              :: полная самопроверка (Live, зрение, поиск, инструменты)
.venv\Scripts\python.exe selftest.py --quick      :: без Live/зрения
.venv\Scripts\python.exe selftest.py --only click :: только поиск элементов на экране (без кликов)
.venv\Scripts\python.exe selftest.py --only new   :: режимы, тихий режим, игры, репетитор, Telegram-агент, Live «вижу экран» и режим словами
.venv\Scripts\python.exe selftest.py --only watch :: 4 способа передать кадр экрана в Live (все рабочие)
.venv\Scripts\python.exe restart_jarvis.py        :: перезапуск запущенного Джарвиса
.venv\Scripts\python.exe tools\make_key.py "Имя"   :: выпустить свой ключ Pro (только у владельца)
```
Отчёт самотеста: `data/selftest_report.txt`. Синтетические записи для теста активации: `data/test/`.
После изменений в `core/` Джарвиса нужно перезапустить (кнопка в «Диагностике» или `restart_jarvis.py`); файлы `ui/` подхватываются при обновлении окна.

## Важные грабли (уже проверено на этом ноутбуке)

- **Никаких консольных окон.** Дочерние процессы — только `pythonw`/`Oswin.exe` или с `creationflags=NO_WINDOW` (0x08000000). Не `DETACHED_PROCESS` для консольных программ и не `cmd /c …`: консольный потомок процесса без консоли открывает чёрное окно (так было с python.exe-лаунчером venv при обновлении). Запускалка — `config.app_exe()` (Oswin.exe → pythonw).
- **Модель «Hey Oswin» (tools/wakeword, Piper en-US):** англ./польск. «Hey Oswin» ≈0.95, но рус. «Эй, Освин» и словацк. «Ahoj Oswin» ≈0.001 — английский TTS не даёт славянского произношения. 2-я попытка (+ варианты osvin/asvin, run 42022621807) хуже: «Hey Austin» 0.996, FP/h 24 — в main оставлена 1-я модель. Дальше: позитивы голосами Piper ru/de/sk/pl + записи живых людей, больше «Austin»-ловушек. Shard 2 генерации (seed 1002) стабильно убивает машину GitHub ~через 17 мин. На ноутбуке пока `wake_engine=google`.
- Окно интерфейса ищется по ТОЧНОМУ заголовку (`brand.is_own_window`): вкладка сайта «Oswin — …» в браузере тоже начинается с «Oswin».

- **Python в .venv — 3.13** (системный 3.15 — для onnxruntime/scipy колёс может не быть). Ставится `setup_jarvis.py` через `py install 3.13`.
- **Не использовать SpeechRecognition / flac.exe** — неподписанный exe блокируется Windows и вешает процесс. STT — сырой PCM в `core/stt.py`.
- **openWakeWord импортирует sklearn** — DLL может блокироваться; в `wake.py` стоит заглушка `openwakeword.custom_verifier_model`.
- **Gemini free tier:** `googleSearch` в Live и grounding в REST → 429 (квота 0). Поэтому поиск — через Edge headless. DuckDuckGo/Bing/Mojeek блокируют ботов.
- Рабочая Live-модель: `gemini-3.8-live` (setup ~0.5 c, первый звук ~0.6 c). `-extended-thinking` требует `thinkingConfig.thinkingLevel`.
  Быстрые текстовые: `gemini-3-flash-preview`, `gemini-3.1-flash-lite`. `gemini-flash-latest` и `3.8-flash` часто 503.
- Схемы функций — строчные типы (`"type": "object"`) работают и в REST, и в Live.
- Эхо: без наушников микрофон глушится, пока Джарвис говорит (`_gated`); перебить можно словом активации. С гарнитурой — полный дуплекс.
- Клики по экрану: два прохода зрения (`box_2d` 0–1000 на всём экране → уточнение по фрагменту). Нужна `SetProcessDpiAwareness(2)`.
- venv-лаунчер `python.exe` запускает дочерний python с той же командной строкой — не убивать процессы «по имени скрипта» без исключения родителя.
- Вывод в консоль: всегда `reconfigure(encoding="utf-8")`, иначе cp1251 падает на символах вроде «≈».
- JSON: оценки openWakeWord — `numpy.float32`, приводить к `float()`.
- Live видит кадры `realtimeInput.video` и при голосе, и при `clientContent`-тексте; но модель должна знать, что режим включён —
  иначе отвечает «экран не транслируется». Поэтому при включении кнопкой отправляется `[СИСТЕМА: …]`.
- В описании `routine_save` не давать пример с `wait` — модель начинает вставлять паузы, о которых не просили.
- Тест-детектор «не вижу»: только с границей слова (`(?<!\w)не вижу`) — «экраНЕ ВИЖУ» даёт ложное срабатывание.

## Бесплатная версия и Pro

- `core/license.py`: `PRO_TOOLS` (routine_*, quiet_mode, watch_screen), `PRO_PERSONAS` (tutor), плюс проактивность/брифинг и Telegram
  проверяют `Assistant.pro`. Gating инструментов — в `Toolbox.call` (возвращает `pro_only`, модель предлагает Pro); UI — класс `body.free` и 🔒.
- Ключи Gumroad: проверка `api.gumroad.com/v2/licenses/verify` (нужен `GUMROAD_PRODUCT_ID` в license.py), раз в 3 дня, офлайн-запас 14 дней.
- Свои ключи `PRO-<payload>.<подпись Ed25519>`: `tools/make_key.py "Имя" [--days N]`. Секрет — `data/license_private.key` ТОЛЬКО на ноутбуке
  владельца (никогда не коммитить, не показывать). Открытый ключ — `PUBLIC_KEY` в license.py; Ed25519 на чистом Python — `core/ed25519.py`.
- Код публичный — защита рассчитана на честных пользователей, не на взлом. Не добавлять сюда «секретов».
- Подключение магазина: создать товар на Gumroad с галочкой «Generate a unique license key», вписать product_id и ссылку
  в `GUMROAD_PRODUCT_ID` / `BUY_URL`, поднять версию.

## Как выпустить обновление

Обновления идут прямо из ветки `main` репозитория `woozermach/Jarvis` (Releases не нужны — из облачной сессии Claude их создавать нельзя).
1. Поднять номер в `VERSION` (например 2.1.1 → 2.2.0) и добавить сверху `CHANGELOG.md` раздел `## 2.2.0 — дата` со списком изменений
   по-русски (этот текст пользователь видит в «Что нового»). Прогнать `selftest.py`.
2. Закоммитить и запушить в `main`. Всё — у установленных Джарвисов в течение 6 часов появится «⬆ ОБНОВИТЬ ДО 2.2.0».
Пока VERSION не поднят, push в main никому ничего не предлагает (можно спокойно коммитить промежуточное).
Не менять аргументы запуска `update_helper.py` без обратной совместимости: его запускает СТАРАЯ версия.
Проверка: `selftest.py --only update`.

## Правила

- **Никогда не коммитить `config.json`, `data/`, `.venv/`, `jarvis.log`** (там ключ и личные данные) — см. `.gitignore`.
- Новый инструмент: описание в `_declarations()` + метод `t_<name>`, при необходимости добавить в группу `TOOL_GROUPS`,
  название в `TOOL_NAMES` (ui/app.js) и проверку в `selftest.py`.
- Новая настройка: DEFAULTS + SCHEMA в config.py, поле в ui/index.html, `fillForm`/`saveSettings` в app.js, применение в `apply_settings`.
- Опасные действия (питание, корзина, клики «купить/удалить») — только с подтверждением, если `confirm_dangerous`.
- После изменений — прогнать `selftest.py` и посмотреть на окно.

## Идеи на будущее

- Штурман ETS2: плагин телеметрии scs-sdk-plugin (shared memory) → скорость, лимит, усталость, груз, заказ → проактивные подсказки. Проверять при запущенной игре.
- Офлайн-режим: Ollama + локальные STT/TTS, когда нет интернета или кончилась квота.

Своё имя/бренд вместо J.A.R.V.I.S. (торговая марка Marvel), установщик .exe и подпись кода, режим «свой ключ» для продажи,
официальные API вместо неофициального STT и поиска через Edge.
