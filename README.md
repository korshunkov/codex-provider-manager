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
| OpenRouter — Ox Alpha | `https://openrouter.ai/api/v1` (`stealth/ox-alpha`) |

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

## Где что лежит

- `src/codex-provider` - основной переключатель.
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
