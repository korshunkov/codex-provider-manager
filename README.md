# Codex Provider Manager

![macOS](https://img.shields.io/badge/macOS-14%2B-black)
![License](https://img.shields.io/badge/license-MIT-green)
[![Tests](https://github.com/korshunkov/codex-provider-manager/actions/workflows/tests.yml/badge.svg)](https://github.com/korshunkov/codex-provider-manager/actions/workflows/tests.yml)

**Codex Provider Manager** is a macOS SwiftUI app and local proxy for managing
Codex model providers, OpenAI-compatible APIs, model catalogs, compatibility
tests, and auto-compaction settings.

Приложение показывает таблицу моделей, проверяет их совместимость, выбирает
модель компакта и направляет запросы через локальный прокси. OpenRouter —
встроенный провайдер и справочник метаданных. Другие OpenAI-совместимые сервисы
можно добавлять в настройках приложения.

## Возможности

- Таблица моделей с ценами, контекстом, индексом качества и выгодностью.
- Отдельная кнопка проверки каждой модели; несколько проверок работают параллельно.
- Галочки для каталога Codex и отдельная модель для компакта.
- Настройка автокомпакта в процентах от контекста модели или в фиксированных токенах.
- Защита Mac от сна во время активной задачи Codex.
- Добавление и удаление OpenAI-совместимых провайдеров.
- Локальный прокси направляет каждую модель своему провайдеру.
- Подключение сторонних агентов к одному локальному адресу через
  Responses API или Chat Completions API.
- Кнопка «Добавить в ZCode» создает или обновляет провайдера ZCode
  со всеми отмеченными моделями.

## Установка

Нужны macOS 14 или новее, Xcode Command Line Tools и Python 3.11+.

```bash
git clone https://github.com/korshunkov/codex-provider-manager.git
cd codex-provider-manager
./build_table_app.sh --install
```

Скрипт собирает приложение «Модели Codex» и ставит команды `codex-provider`,
`codex-provider-proxy` и `codex-power-watch` в `~/.codex/bin`.

## Начало работы

1. Откройте приложение «Модели Codex».
2. Нажмите «Настройки» и добавьте API-ключ OpenRouter.
3. Добавьте своих провайдеров: приложение сразу проверит, что список моделей доступен.
4. Отметьте нужные модели и нажмите «Включить выбранные».
5. В настройках выберите модель компакта и уровень автокомпакта.

## Автокомпакт

Есть два режима:

- **Процент** — используется процент от максимального контекста выбранной модели.
- **Токены** — задаётся одна граница, например 200 000 токенов.

Значение записывается в каталог моделей Codex через поле
`effective_context_window_percent`. Поэтому для моделей с разным контекстом
фиксированный лимит автоматически превращается в подходящий процент.

## Данные моделей

Приложение сначала использует данные самого провайдера. Если провайдер не отдаёт
контекст, уровни рассуждений или оценки качества, программа ищет одно однозначное
совпадение по имени модели в OpenRouter.

Возможные пометки:

- серая галочка — данные пришли от провайдера;
- синяя «i» — часть данных взята из OpenRouter;
- жёлтый предупреждение — надёжных данных нет, используются безопасные значения.

Цена никогда не переносится из OpenRouter в другой провайдер.

## Команды

```bash
codex-provider list
codex-provider current
codex-provider models openrouter-all
codex-provider provider-settings
codex-provider set-auto-compact --mode percent --value 75
codex-provider proxy status
codex-provider proxy start
codex-provider proxy stop
codex-power-watch status
```

При запуске приложения прокси автоматически обновляется до текущей версии скрипта.
Кнопка «Применить и перезапустить Codex» также перезапускает только прокси,
принадлежащий этому менеджеру, и ждёт его готовности. Чужой процесс на порту
8765 менеджер не завершает.

## Подключение других агентов

Когда прокси включен, сторонний агент может использовать локальный адрес:

```text
http://127.0.0.1:8765/v1
```

Прокси отдает выбранные модели через `GET /v1/models`, принимает
`POST /v1/responses` и `POST /v1/chat/completions`. Имена моделей нужно брать
из приложения, например `or/z-ai/glm-5.3`. Поле API-ключа у агента можно
заполнить любым непустым значением: прокси сам подставляет настоящий ключ
нужного провайдера.

Для нового провайдера выберите тип API: `Responses`, если у сервиса есть
`/responses`, или `Chat Completions`, если он поддерживает только
`/chat/completions`. Через командную строку тип задается так:

```bash
codex-provider provider-add --label "My AI" --prefix myai \
  --base-url https://api.example.com/v1 --api-mode chat --api-key-stdin
```

Кнопка «Добавить в ZCode» отправляет в ZCode все модели, отмеченные
галочками. Если провайдер уже создан, его список моделей будет заменен новым
выбором. После обновления перезапустите ZCode, если он был открыт.

## Приватность и ключи

API-ключи хранятся в закрытом файле `~/.codex/provider-credentials.json` с правами
`600`. Локальный прокси слушает только `127.0.0.1` и не пишет содержимое запросов
или ответов в лог.

## Разработка

```bash
python3 -m unittest discover -s tests -v
./build_table_app.sh
```

## Лицензия

Проект распространяется по лицензии MIT. Подробности — в файле `LICENSE`.
