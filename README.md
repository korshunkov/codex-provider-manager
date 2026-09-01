# Менеджер провайдеров Codex

Небольшое приложение для macOS и команда `codex-provider`. Они переключают
сервис, через который Codex обращается к модели, без ручного редактирования
настроек.

## Что настроено

| Сервис | Адрес API |
| --- | --- |
| Codex Sale | `https://codex.sale/backend-api/codex` |
| VibeCode | `https://vibecode.moe/v1` |
| AnyModel | `https://anymodel.org/v1` |
| A6 API | `https://api.a6api.com/v1` |
| OpenRouter — бесплатные модели | `https://openrouter.ai/api/v1` |

Все новые задачи Codex записываются с единым внутренним идентификатором
`codex-sale`. Поэтому смена сервиса не создаёт отдельную группу сессий.

Для Codex Sale переключатель использует его штатную авторизацию через
`~/.codex/auth.json`; это важно для полноценного режима Codex с инструментами.

## Как пользоваться

Самый простой вариант - открыть приложение
`/Users/admin/Applications/Codex Provider.app` и выбрать сервис. После
успешного выбора приложение само принудительно перезапустит Codex.

Также доступны команды:

```bash
codex-provider list
codex-provider current
codex-provider use a6api
codex-provider use anymodel
codex-provider use vibecode
codex-provider use codex-sale
codex-provider use openrouter
```

Команда `codex-provider use <сервис> --keep-model` переключает только сервис,
не меняя выбранную модель.

## Выбор моделей

Приложение сначала предлагает выбрать провайдера, а затем найти модель по
части названия. Пустой поиск показывает компактную рабочую полку: текущую,
недавние, избранные и рекомендуемые модели. В стандартный переключатель Codex
попадает не более 30 моделей, поэтому сотни позиций провайдера не перегружают
интерфейс.

Для OpenRouter загружаются только бесплатные текстовые модели с поддержкой
инструментов. Платные модели отсекаются до создания каталога Codex.

Полезные команды:

```bash
codex-provider models anymodel --search GLM
codex-provider models openrouter
codex-provider select-model glm/glm-5.3
codex-provider favorite glm/glm-5.3
codex-provider favorite glm/glm-5.3 --remove
codex-provider use anymodel --model glm/glm-5.3
```

Менеджер запоминает последнюю модель отдельно для каждого провайдера. Если
текущая модель есть у нового провайдера, при переключении она сохраняется.
У каждой модели в каталоге указаны только доступные ей уровни рассуждения.

## Где что лежит

- `src/codex-provider` - основной переключатель.
- `src/provider_models.py` - загрузка, поиск и компактный каталог моделей.
- `src/codex-provider-key` - выдаёт нужный ключ только самому Codex.
- `src/CodexProvider.applescript` - исходник окна с выбором сервиса.
- `dist/Провайдер Codex.app` - собранная копия приложения.

Ключи не хранятся в этой папке и не попадают в исходники. Они находятся в
закрытом файле `~/.codex/provider-credentials.json`; доступ к нему есть только
у владельца Mac.

## Сборка после изменения окна

```bash
mkdir -p "/private/tmp/codex-provider-build"
osacompile -o "/private/tmp/codex-provider-build/Провайдер Codex.app" "src/CodexProvider.applescript"
```

После успешной сборки замените приложение в папке `Программы` новой копией.

## История версий

Проект хранится в локальном Git-репозитории. Перед крупными изменениями
создаётся отдельный коммит, поэтому рабочую версию можно восстановить.
