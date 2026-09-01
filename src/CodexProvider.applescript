on selectedService()
	set knownServices to {"codex-sale", "vibecode", "anymodel", "a6api", "openrouter"}
	try
		set currentResult to do shell script "/Users/admin/.local/bin/codex-provider current"
		repeat with serviceName in knownServices
			if currentResult contains ("Текущий сервис: " & serviceName) then return serviceName as text
		end repeat
	end try
	return "codex-sale"
end selectedService

on displayNameFor(serviceName)
	if serviceName is "codex-sale" then return "Codex Sale"
	if serviceName is "vibecode" then return "VibeCode"
	if serviceName is "anymodel" then return "AnyModel"
	if serviceName is "a6api" then return "A6 API"
	return "OpenRouter — Ox Alpha"
end displayNameFor

on serviceFor(displayName)
	if displayName is "Codex Sale" then return "codex-sale"
	if displayName is "VibeCode" then return "vibecode"
	if displayName is "AnyModel" then return "anymodel"
	if displayName is "A6 API" then return "a6api"
	return "openrouter"
end serviceFor

set activeService to selectedService()
set defaultChoice to displayNameFor(activeService)
set choices to {"Codex Sale", "VibeCode", "AnyModel", "A6 API", "OpenRouter — Ox Alpha"}

set chosenItems to choose from list choices with title "Провайдер Codex" with prompt "Выберите сервис для следующих задач Codex:" default items {defaultChoice} OK button name "Выбрать" cancel button name "Отмена"

if chosenItems is false then return

set chosenName to item 1 of chosenItems
set chosenService to serviceFor(chosenName)

try
	do shell script "/Users/admin/.local/bin/codex-provider use " & quoted form of chosenService
	do shell script "/usr/bin/pkill -x ChatGPT >/dev/null 2>&1 || true"
	delay 3
	do shell script "/usr/bin/open -a ChatGPT"
on error errorMessage
	display dialog "Не удалось изменить провайдера:" & return & return & errorMessage with title "Провайдер Codex" buttons {"Закрыть"} default button "Закрыть" with icon stop
end try
