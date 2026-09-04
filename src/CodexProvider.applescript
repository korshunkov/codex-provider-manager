on selectedService()
	set knownServices to {"codex-sale", "vibecode", "anymodel", "a6api", "openrouter"}
	try
		set currentResult to do shell script "$HOME/.local/bin/codex-provider current"
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
	return "OpenRouter — только бесплатные"
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
set choices to {"Codex Sale", "VibeCode", "AnyModel", "A6 API", "OpenRouter — только бесплатные"}

set chosenItems to choose from list choices with title "Провайдер Codex" with prompt "Выберите сервис для следующих задач Codex:" default items {defaultChoice} OK button name "Выбрать" cancel button name "Отмена"

if chosenItems is false then return

set chosenName to item 1 of chosenItems
set chosenService to serviceFor(chosenName)

try
	set searchDialog to display dialog "Введите часть названия модели, например GLM или GPT." & return & return & "Оставьте поле пустым, чтобы показать избранные, недавние и рекомендуемые модели." with title "Модель Codex" default answer "" buttons {"Отмена", "Найти"} default button "Найти" cancel button "Отмена"
	set searchText to text returned of searchDialog
	set modelResult to do shell script "$HOME/.local/bin/codex-provider models " & quoted form of chosenService & " --search " & quoted form of searchText & " --format tsv --limit 50"
	if modelResult is "" then
		display dialog "Подходящие модели не найдены." with title "Модель Codex" buttons {"Закрыть"} default button "Закрыть" with icon caution
		return
	end if

	set modelIds to {}
	set modelLabels to {}
	set oldDelimiters to AppleScript's text item delimiters
	repeat with modelLine in paragraphs of modelResult
		set AppleScript's text item delimiters to tab
		set modelParts to text items of (modelLine as text)
		if (count of modelParts) is greater than 1 then
			set end of modelIds to item 1 of modelParts
			set end of modelLabels to item 2 of modelParts
		end if
	end repeat
	set AppleScript's text item delimiters to oldDelimiters

	set chosenModels to choose from list modelLabels with title "Модель Codex" with prompt "Выберите модель для " & chosenName & ":" OK button name "Выбрать" cancel button name "Отмена"
	if chosenModels is false then return
	set chosenModelLabel to item 1 of chosenModels
	set chosenModelId to ""
	repeat with modelIndex from 1 to count of modelLabels
		if item modelIndex of modelLabels is chosenModelLabel then
			set chosenModelId to item modelIndex of modelIds
			exit repeat
		end if
	end repeat
	if chosenModelId is "" then error "Не удалось определить выбранную модель."

	do shell script "$HOME/.local/bin/codex-provider use " & quoted form of chosenService & " --model " & quoted form of chosenModelId
	do shell script "/usr/bin/pkill -x ChatGPT >/dev/null 2>&1 || true"
	delay 3
	do shell script "/usr/bin/open -a ChatGPT"
on error errorMessage number errorNumber
	if errorNumber is -128 then return
	display dialog "Не удалось изменить провайдера или модель:" & return & return & errorMessage with title "Провайдер Codex" buttons {"Закрыть"} default button "Закрыть" with icon stop
end try
