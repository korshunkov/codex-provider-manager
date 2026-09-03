
import SwiftUI

struct ModelRow: Identifiable, Decodable, Hashable {
    private let modelIdentifier: String
    let displayName: String
    let modelDescription: String
    let contextWindow: Int
    let inputPrice: Double?
    let outputPrice: Double?
    let pricesAreEstimated: Bool
    let intelligenceIndex: Double?
    let codingIndex: Double?
    let agenticIndex: Double?

    var providerID: String? = nil
    var providerName: String? = nil

    var id: String { "\(providerID ?? "single")|\(modelIdentifier)" }
    var modelID: String { modelIdentifier }
    var providerNameSort: String { (providerName ?? "").lowercased() }

    enum CodingKeys: String, CodingKey {
        case modelIdentifier = "id"
        case displayName = "display_name"
        case modelDescription = "description"
        case contextWindow = "context_window"
        case inputPrice = "input_price_per_million"
        case outputPrice = "output_price_per_million"
        case pricesAreEstimated = "price_is_estimate"
        case intelligenceIndex = "intelligence_index"
        case codingIndex = "coding_index"
        case agenticIndex = "agentic_index"
    }

    var nameSort: String { displayName.lowercased() }
    var inputSort: Double { inputPrice ?? .infinity }
    var outputSort: Double { outputPrice ?? .infinity }
    /// Codex-weighted Artificial Analysis score: agent work matters most,
    /// then coding, then general reasoning.
    var codexIndex: Double? {
        guard let agenticIndex, let codingIndex, let intelligenceIndex else { return nil }
        return agenticIndex * 0.5 + codingIndex * 0.3 + intelligenceIndex * 0.2
    }

    var indexSort: Double { codexIndex ?? -.infinity }

    var weightedCost: Double? {
        guard let inputPrice, let outputPrice else { return nil }
        return inputPrice * 0.8 + outputPrice * 0.2
    }

    var valueScore: Double? {
        guard let weightedCost, weightedCost > 0, let codexIndex else { return nil }
        return codexIndex / weightedCost
    }

    var isTopFree: Bool {
        inputPrice == 0 && outputPrice == 0 && (codexIndex ?? 0) > 40
    }

    var valueSort: Double {
        if isTopFree { return .greatestFiniteMagnitude }
        return valueScore ?? -.infinity
    }
    var contextSort: Int { contextWindow }

    var inputText: String { Self.price(inputPrice, estimated: pricesAreEstimated) }
    var outputText: String { Self.price(outputPrice, estimated: pricesAreEstimated) }
    var indexText: String { codexIndex.map { String(format: "%.1f", $0) } ?? "—" }
    var valueText: String {
        if isTopFree { return "★" }
        return (pricesAreEstimated ? "~" : "") + (valueScore.map { String(format: "%.0f", $0) } ?? "—")
    }
    var contextText: String { "\(contextWindow / 1000)K" }

    static func price(_ value: Double?, estimated: Bool = false) -> String {
        guard let value else { return "—" }
        if value == 0 { return "бесплатно" }
        return (estimated ? "~" : "") + String(format: "$%.3f", value)
    }
}

struct ModelResponse: Decodable {
    let provider: String
    let label: String
    let currentModel: String
    let models: [ModelRow]

    enum CodingKeys: String, CodingKey {
        case provider
        case label
        case currentModel = "current_model"
        case models
    }
}

struct ModelTestResponse: Decodable {
    let ok: Bool
    let message: String
    let attempts: Int?
}

struct ProviderOption: Hashable, Identifiable {
    let id: String
    let name: String
}

struct ProxySelection: Codable, Hashable {
    let providerID: String
    let modelID: String

    enum CodingKeys: String, CodingKey {
        case providerID = "provider_id"
        case modelID = "model_id"
    }

    var key: String { "\(providerID)|\(modelID)" }
}

struct ProxyStateResponse: Decodable {
    let running: Bool
    let selected: [ProxySelection]
    let compactionModel: ProxySelection?

    enum CodingKeys: String, CodingKey {
        case running
        case selected
        case compactionModel = "compaction_model"
    }
}

struct ProxyApplyResponse: Decodable {
    let activeModel: String
    let warnings: [String]?

    enum CodingKeys: String, CodingKey {
        case activeModel = "active_model"
        case warnings
    }
}

struct PowerWatchStateResponse: Decodable {
    let running: Bool
    let codexActive: Bool
    let batterySleepDisabled: Bool
    let networkAvailable: Bool
    let networkMissingSeconds: Int
    let networkSleepRequested: Bool
    let updatedAt: String?

    enum CodingKeys: String, CodingKey {
        case running
        case codexActive = "codex_active"
        case batterySleepDisabled = "battery_sleep_disabled"
        case networkAvailable = "network_available"
        case networkMissingSeconds = "network_missing_seconds"
        case networkSleepRequested = "network_sleep_requested"
        case updatedAt = "updated_at"
    }
}

enum PriceFilter: String, CaseIterable, Identifiable {
    case all
    case selected
    case withPrice
    case free
    case withIndex

    var id: String { rawValue }
    var title: String {
        switch self {
        case .all: "Все модели"
        case .selected: "Выбранные"
        case .withPrice: "С ценой"
        case .free: "Бесплатные"
        case .withIndex: "С индексом"
        }
    }
}

@MainActor
final class ModelStore: ObservableObject {
    @Published var providerID = "all"
    @Published var rows: [ModelRow] = []
    @Published var selectedRowID: String?
    @Published var status = "Нажмите «Обновить», чтобы загрузить модели."
    @Published var isLoading = false
    @Published var currentModel = ""
    @Published var selectedModels: [ProxySelection] = []
    @Published var compactionModel: ProxySelection?
    @Published var proxyRunning = false
    @Published var powerWatchRunning = false
    @Published var powerWatchCodexActive = false
    @Published var powerWatchNetworkAvailable = true
    @Published var powerWatchNetworkMissingSeconds = 0
    @Published var powerWatchStatus = "Защита от сна выключена."
    @Published var isPowerWatchBusy = false

    let providers = [
        ProviderOption(id: "all", name: "Все провайдеры"),
        ProviderOption(id: "codex-sale", name: "Codex Sale"),
        ProviderOption(id: "vibecode", name: "VibeCode"),
        ProviderOption(id: "anymodel", name: "AnyModel"),
        ProviderOption(id: "a6api", name: "A6 API"),
        ProviderOption(id: "openrouter-all", name: "OpenRouter — все"),
        ProviderOption(id: "openrouter", name: "OpenRouter — бесплатные"),
    ]

    private let allProviderIDs = [
        "codex-sale", "vibecode", "anymodel", "a6api", "openrouter-all",
    ]

    private let cliURL = URL(fileURLWithPath: "/Users/admin/.local/bin/codex-provider")
    private let powerWatchURL = URL(fileURLWithPath: "/Users/admin/.codex/bin/codex-power-watch")

    func loadProxyState() {
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            let result = Self.runProcess(self?.cliURL, arguments: ["proxy", "status"])
            DispatchQueue.main.async {
                guard let self else { return }
                switch result {
                case .success(let output):
                    do {
                        let state = try JSONDecoder().decode(ProxyStateResponse.self, from: output)
                        self.proxyRunning = state.running
                        self.selectedModels = state.selected
                        self.compactionModel = state.compactionModel
                    } catch {
                        self.status = "Не удалось прочитать выбор прокси: \(error.localizedDescription)"
                    }
                case .failure(.message(let error)):
                    self.status = "Прокси недоступен: \(error)"
                }
            }
        }
    }

    func loadPowerWatchState() {
        guard !isPowerWatchBusy else { return }
        DispatchQueue.global(qos: .utility).async { [weak self] in
            let result = Self.runProcess(self?.powerWatchURL, arguments: ["status", "--json"])
            DispatchQueue.main.async {
                guard let self else { return }
                switch result {
                case .success(let output):
                    do {
                        let state = try JSONDecoder().decode(PowerWatchStateResponse.self, from: output)
                        self.applyPowerWatchState(state)
                    } catch {
                        self.powerWatchRunning = false
                        self.powerWatchStatus = "Не удалось прочитать состояние защиты от сна."
                    }
                case .failure(.message(let error)):
                    self.powerWatchRunning = false
                    self.powerWatchStatus = "Защита от сна недоступна: \(error)"
                }
            }
        }
    }

    private func applyPowerWatchState(_ state: PowerWatchStateResponse) {
        powerWatchRunning = state.running
        powerWatchCodexActive = state.codexActive
        powerWatchNetworkAvailable = state.networkAvailable
        powerWatchNetworkMissingSeconds = state.networkMissingSeconds

        guard state.running else {
            powerWatchStatus = "Защита от сна выключена."
            return
        }

        let codex = state.codexActive ? "Codex активен" : "Codex не активен"
        let network = state.networkAvailable
            ? "сеть есть"
            : "сети нет \(state.networkMissingSeconds) сек"
        let sleep = state.batterySleepDisabled ? "; сон запрещён" : ""
        let pending = state.networkSleepRequested ? "; отправлен в сон" : ""
        powerWatchStatus = "\(codex), \(network)\(sleep)\(pending)."
    }

    func setPowerWatch(_ enabled: Bool) {
        guard !isPowerWatchBusy, powerWatchRunning != enabled else { return }
        isPowerWatchBusy = true
        powerWatchRunning = enabled
        powerWatchStatus = enabled ? "Включаю защиту от сна…" : "Выключаю защиту от сна…"

        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            let result = Self.runProcess(self?.powerWatchURL, arguments: [enabled ? "start" : "stop"])
            DispatchQueue.main.async {
                guard let self else { return }
                self.isPowerWatchBusy = false
                switch result {
                case .success(let output):
                    let message = String(data: output, encoding: .utf8)?
                        .trimmingCharacters(in: .whitespacesAndNewlines)
                    if let message, !message.isEmpty {
                        self.powerWatchStatus = message.replacingOccurrences(of: "\n", with: " ")
                    }
                    self.loadPowerWatchState()
                case .failure(.message(let error)):
                    self.powerWatchStatus = error
                    self.loadPowerWatchState()
                }
            }
        }
    }

    func load(refresh: Bool = false) {
        if providerID == "all" {
            loadAllProviders(refresh: refresh)
        } else {
            loadOneProvider(refresh: refresh)
        }
    }

    private func loadOneProvider(refresh: Bool) {
        isLoading = true
        status = "Загружаю модели…"
        var arguments = ["models", providerID, "--format", "json", "--limit", "10000"]
        if refresh { arguments.append("--refresh") }

        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            let result = Self.runProcess(self?.cliURL, arguments: arguments)
            DispatchQueue.main.async {
                guard let self else { return }
                self.isLoading = false
                switch result {
                case .success(let output):
                    do {
                        let decoded = try JSONDecoder().decode(ModelResponse.self, from: output)
                        let providerName = self.providers.first { $0.id == decoded.provider }?.name ?? decoded.label
                        self.rows = self.decorated(decoded.models, providerID: decoded.provider, providerName: providerName)
                        self.currentModel = decoded.currentModel
                        self.selectedRowID = self.rows.first { $0.modelID == decoded.currentModel }?.id
                        self.status = "\(providerName): \(self.rows.count) моделей. Текущая: \(decoded.currentModel)."
                    } catch {
                        self.status = "Не удалось разобрать ответ: \(error.localizedDescription)"
                    }
                case .failure(.message(let error)):
                    self.rows = []
                    self.status = error
                }
            }
        }
    }

    private func loadAllProviders(refresh: Bool) {
        isLoading = true
        status = "Загружаю все провайдеры…"
        let providers = self.allProviderIDs

        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            var responses: [ModelResponse] = []
            var failures: [String] = []

            for (index, providerID) in providers.enumerated() {
                DispatchQueue.main.async {
                    self?.status = "Загружаю провайдера \(index + 1) из \(providers.count)…"
                }
                var arguments = ["models", providerID, "--format", "json", "--limit", "10000"]
                if refresh { arguments.append("--refresh") }
                let result = Self.runProcess(self?.cliURL, arguments: arguments)
                switch result {
                case .success(let output):
                    do {
                        responses.append(try JSONDecoder().decode(ModelResponse.self, from: output))
                    } catch {
                        failures.append("\(providerID): \(error.localizedDescription)")
                    }
                case .failure(.message(let error)):
                    failures.append("\(providerID): \(error)")
                }
            }

            DispatchQueue.main.async {
                guard let self else { return }
                self.isLoading = false
                self.rows = responses.flatMap { response in
                    let providerName = self.providers.first { $0.id == response.provider }?.name ?? response.label
                    return self.decorated(response.models, providerID: response.provider, providerName: providerName)
                }
                self.currentModel = responses.first(where: { $0.provider != "all" })?.currentModel ?? ""
                self.selectedRowID = nil

                if failures.isEmpty {
                    self.status = "Все провайдеры: \(self.rows.count) моделей. Выберите строку, чтобы применить её сервис."
                } else {
                    let names = failures.joined(separator: "; ")
                    self.status = "Все провайдеры: \(self.rows.count) моделей. Не загружены: \(names)."
                }
            }
        }
    }

    private func decorated(_ models: [ModelRow], providerID: String, providerName: String) -> [ModelRow] {
        models.map { model in
            var row = model
            row.providerID = providerID
            row.providerName = providerName
            return row
        }
    }

    var selectedRow: ModelRow? {
        rows.first { $0.id == selectedRowID }
    }

    func selection(for row: ModelRow) -> ProxySelection {
        ProxySelection(providerID: row.providerID ?? providerID, modelID: row.modelID)
    }

    func isSelected(_ row: ModelRow) -> Bool {
        selectedModels.contains { $0.key == selection(for: row).key }
    }

    func setSelection(_ row: ModelRow, enabled: Bool) {
        let item = selection(for: row)
        selectedModels.removeAll { $0.key == item.key }
        if enabled {
            selectedModels.append(item)
        }
    }

    func clearSelection() {
        selectedModels.removeAll()
        status = "Галочки сняты. Нажмите «Включить выбранные», чтобы сохранить изменения."
    }

    func selectionLabel(_ item: ProxySelection?) -> String {
        guard let item else { return "Не выбрана" }
        if let row = rows.first(where: { $0.providerID == item.providerID && $0.modelID == item.modelID }) {
            return row.displayName
        }
        return item.modelID
    }

    func applySelection() {
        guard !selectedModels.isEmpty else { return }
        isLoading = true
        status = "Включаю выбранные модели в конфиг…"
        let active = selectedRow.flatMap { selection(for: $0) }
        var payload: [String: Any] = [
            "models": selectedModels.map { ["provider_id": $0.providerID, "model_id": $0.modelID] },
        ]
        if let compactionModel {
            payload["compaction_model"] = [
                "provider_id": compactionModel.providerID,
                "model_id": compactionModel.modelID,
            ]
        } else {
            payload["compaction_model"] = NSNull()
        }
        if let active {
            payload["active_model"] = [
                "provider_id": active.providerID,
                "model_id": active.modelID,
            ]
        }
        let data: Data
        do {
            data = try JSONSerialization.data(withJSONObject: payload)
        } catch {
            isLoading = false
            status = "Не удалось создать запрос: \(error.localizedDescription)"
            return
        }
        let arguments = ["proxy", "configure", "--stdin"]

        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            let result = Self.runProcess(self?.cliURL, arguments: arguments, stdin: data)
            DispatchQueue.main.async {
                guard let self else { return }
                switch result {
                case .success(let output):
                    do {
                        let decoded = try JSONDecoder().decode(ProxyApplyResponse.self, from: output)
                        let warning = decoded.warnings?.isEmpty == false ? " \(decoded.warnings!.joined(separator: " "))" : ""
                        self.status = "Выбор применён. Активная: \(decoded.activeModel).\(warning) Перезапускаю Codex…"
                        self.loadProxyState()
                        self.restartCodex()
                    } catch {
                        self.isLoading = false
                        self.status = "Не удалось разобрать ответ прокси: \(error.localizedDescription)"
                    }
                case .failure(.message(let error)):
                    self.isLoading = false
                    self.status = error
                }
            }
        }
    }

    func selectCurrentRow() {
        guard let row = selectedRow else { return }
        let rowSelection = selection(for: row)
        setSelection(row, enabled: true)
        isLoading = true
        status = "Делаю модель активной…"
        let arguments = ["proxy", "select", rowSelection.providerID, "--model", rowSelection.modelID]

        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            let result = Self.runProcess(self?.cliURL, arguments: arguments)
            DispatchQueue.main.async {
                guard let self else { return }
                switch result {
                case .success:
                    self.status = "Модель выбрана. Перезапускаю Codex…"
                    self.loadProxyState()
                    self.restartCodex()
                case .failure(.message(let error)):
                    self.isLoading = false
                    self.status = error
                }
            }
        }
    }

    func testCurrentRow() {
        guard let row = selectedRow else { return }
        isLoading = true
        status = "Проверяю модель потоковым запросом…"
        let provider = row.providerID ?? providerID
        let arguments = ["test-model", provider, "--model", row.modelID]

        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            let result = Self.runProcess(self?.cliURL, arguments: arguments)
            DispatchQueue.main.async {
                guard let self else { return }
                self.isLoading = false
                switch result {
                case .success(let output):
                    do {
                        let decoded = try JSONDecoder().decode(ModelTestResponse.self, from: output)
                        self.status = decoded.ok ? "Проверка пройдена: \(decoded.message)" : "Проверка не пройдена: \(decoded.message)"
                    } catch {
                        self.status = "Проверка вернула непонятный ответ: \(error.localizedDescription)"
                    }
                case .failure(.message(let error)):
                    self.status = "Проверка не выполнена: \(error)"
                }
            }
        }
    }

    private func restartCodex() {
        DispatchQueue.global(qos: .utility).asyncAfter(deadline: .now() + 0.2) {
            let script = "/usr/bin/pkill -x ChatGPT >/dev/null 2>&1 || true; sleep 3; /usr/bin/open -a ChatGPT"
            _ = Self.runProcess(URL(fileURLWithPath: "/bin/zsh"), arguments: ["-c", script])
            DispatchQueue.main.async {
                self.isLoading = false
                self.status = "Модель применена, Codex перезапущен."
            }
        }
    }

    private enum ProcessError: Error {
        case message(String)
    }

    nonisolated private static func runProcess(
        _ executableURL: URL?,
        arguments: [String],
        stdin: Data? = nil
    ) -> Result<Data, ProcessError> {
        guard let executableURL else { return .failure(.message("Не задан путь к codex-provider.")) }
        let process = Process()
        let output = Pipe()
        let errors = Pipe()
        process.executableURL = executableURL
        process.arguments = arguments
        process.standardOutput = output
        process.standardError = errors
        if let stdin {
            let input = Pipe()
            process.standardInput = input
            input.fileHandleForWriting.write(stdin)
            input.fileHandleForWriting.closeFile()
        }

        do {
            try process.run()
            let data = output.fileHandleForReading.readDataToEndOfFile()
            let errorData = errors.fileHandleForReading.readDataToEndOfFile()
            process.waitUntilExit()
            if process.terminationStatus == 0 { return .success(data) }
            let message = String(data: errorData, encoding: .utf8) ?? "Команда завершилась с ошибкой."
            return .failure(.message(message.trimmingCharacters(in: .whitespacesAndNewlines)))
        } catch {
            return .failure(.message(error.localizedDescription))
        }
    }
}

struct ContentView: View {
    @StateObject private var store = ModelStore()
    @State private var searchText = ""
    @State private var priceFilter: PriceFilter = .all
    @State private var sortOrder = [KeyPathComparator(\ModelRow.valueSort, order: .reverse)]
    @State private var showsCompactionPicker = false
    @State private var compactionSearch = ""
    @State private var pinnedSelectionKeys: Set<String> = []

    private var compactionChoices: [ModelRow] {
        let selected = store.selectedModels
        let selectedRows = store.rows.filter { row in
            guard let providerID = row.providerID else { return false }
            return selected.contains { $0.providerID == providerID && $0.modelID == row.modelID }
        }
        return selectedRows.isEmpty ? store.rows : selectedRows
    }

    private var searchableCompactionChoices: [ModelRow] {
        let words = compactionSearch.split(separator: " ").map { $0.lowercased() }
        guard !words.isEmpty else { return compactionChoices }
        return compactionChoices.filter { row in
            let haystack = "\(row.displayName) \(row.modelID) \(row.providerName ?? "")".lowercased()
            return words.allSatisfy { haystack.contains($0) }
        }
    }

    private var filteredRows: [ModelRow] {
        let words = searchText.split(separator: " ").map { $0.lowercased() }
        let rows = store.rows.filter { row in
            let haystack = "\(row.displayName) \(row.modelID) \(row.modelDescription) \(row.providerName ?? "")".lowercased()
            let matchesText = words.allSatisfy { haystack.contains($0) }
            let matchesFilter: Bool
            switch priceFilter {
            case .all: matchesFilter = true
            case .selected:
                let selectionKey = "\(row.providerID ?? "single")|\(row.modelID)"
                matchesFilter = store.isSelected(row) || pinnedSelectionKeys.contains(selectionKey)
            case .withPrice: matchesFilter = row.inputPrice != nil || row.outputPrice != nil
            case .free: matchesFilter = row.inputPrice == 0 || row.outputPrice == 0
            case .withIndex: matchesFilter = row.codexIndex != nil
            }
            return matchesText && matchesFilter
        }
        return rows.sorted(using: sortOrder)
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Picker("Сервис:", selection: $store.providerID) {
                    ForEach(store.providers) { provider in
                        Text(provider.name).tag(provider.id)
                    }
                }
                .frame(maxWidth: 280)
                .onChange(of: store.providerID) { _, _ in store.load() }

                Picker("", selection: $priceFilter) {
                    ForEach(PriceFilter.allCases) { filter in
                        Text(filter.title).tag(filter)
                    }
                }
                .frame(maxWidth: 180)
                .help("«Выбранные»: после снятия галочки модель остаётся в списке до смены фильтра")
                .onChange(of: priceFilter) { _, newValue in
                    if newValue != .selected {
                        pinnedSelectionKeys.removeAll()
                    }
                }

                TextField("Поиск: GLM, GPT, Claude…", text: $searchText)
                    .textFieldStyle(.roundedBorder)

                Button("Обновить") {
                    store.load(refresh: true)
                }
                .disabled(store.isLoading)
            }
            .padding()
            .background(.bar)

            Table(filteredRows, selection: $store.selectedRowID, sortOrder: $sortOrder) {
                TableColumn("") { row in
                    Toggle(
                        "",
                        isOn: Binding(
                            get: { store.isSelected(row) },
                            set: { enabled in
                                if enabled, priceFilter == .selected {
                                    pinnedSelectionKeys.insert("\(row.providerID ?? "single")|\(row.modelID)")
                                }
                                store.setSelection(row, enabled: enabled)
                            }
                        )
                    )
                    .labelsHidden()
                }
                .width(34)

                TableColumn("Провайдер", value: \.providerNameSort) { row in
                    Text(row.providerName ?? "—")
                        .lineLimit(2)
                }
                .width(min: 130, ideal: 170)

                TableColumn("Модель", value: \.nameSort) { row in
                    VStack(alignment: .leading, spacing: 2) {
                        Text(row.displayName)
                            .lineLimit(1)
                        Text(row.modelID)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }
                }
                .width(min: 220, ideal: 320)

                TableColumn("Вход $/M", value: \.inputSort) { row in
                    Text(row.inputText)
                        .monospacedDigit()
                        .help(row.pricesAreEstimated ? "Примерно: средняя цена дешёвой половины каналов A6" : "")
                }
                .width(min: 80, ideal: 105)

                TableColumn("Выход $/M", value: \.outputSort) { row in
                    Text(row.outputText)
                        .monospacedDigit()
                        .help(row.pricesAreEstimated ? "Примерно: средняя цена дешёвой половины каналов A6" : "")
                }
                .width(min: 80, ideal: 105)

                TableColumn("Индекс Codex", value: \.indexSort) { row in
                    Text(row.indexText)
                        .monospacedDigit()
                        .help("Agentic × 0.5 + Coding × 0.3 + Intelligence × 0.2")
                }
                .width(min: 105, ideal: 125)

                TableColumn("Выгодность", value: \.valueSort) { row in
                    Text(row.valueText)
                        .monospacedDigit()
                        .foregroundStyle(row.isTopFree ? .yellow : .primary)
                        .fontWeight(row.isTopFree || row.valueScore != nil ? .medium : .regular)
                        .help(row.isTopFree
                              ? "Бесплатная модель с индексом Codex выше 40"
                              : "Индекс Codex ÷ условная цена (80% входа, 20% выхода)")
                }
                .width(min: 95, ideal: 110)

                TableColumn("Контекст", value: \.contextSort) { row in
                    Text(row.contextText).monospacedDigit()
                }
                .width(min: 80, ideal: 95)
            }
            .padding(.horizontal, 8)

            HStack {
                Text(store.status)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
                Spacer()
            }
            .padding(.horizontal)
            .padding(.top, 10)

            HStack(spacing: 10) {
                Toggle("Защита от сна", isOn: Binding(
                    get: { store.powerWatchRunning },
                    set: { store.setPowerWatch($0) }
                ))
                .toggleStyle(.switch)
                .disabled(store.isPowerWatchBusy)
                .help("Пока Codex работает, Mac не засыпает. Если сеть недоступна более минуты, Mac уходит в сон.")

                Text(store.powerWatchStatus)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)

                Spacer()
            }
            .padding(.horizontal)
            .padding(.bottom, 4)

            HStack(spacing: 12) {
                Text("Выбрано: \(store.selectedModels.count)")
                    .fontWeight(.medium)

                Button {
                    showsCompactionPicker = true
                } label: {
                    Label(
                        "Компакт: \(store.selectionLabel(store.compactionModel))",
                        systemImage: "arrow.down.circle"
                    )
                    .lineLimit(1)
                }
                .buttonStyle(.bordered)
                .popover(isPresented: $showsCompactionPicker, arrowEdge: .top) {
                    VStack(alignment: .leading, spacing: 0) {
                        TextField("Поиск модели…", text: $compactionSearch)
                            .textFieldStyle(.roundedBorder)
                            .padding(10)
                        Divider()
                        List(searchableCompactionChoices) { row in
                            Button {
                                store.compactionModel = store.selection(for: row)
                                showsCompactionPicker = false
                                compactionSearch = ""
                            } label: {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(row.displayName).lineLimit(1)
                                    Text("\(row.providerName ?? "") · \(row.modelID)")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                        .lineLimit(1)
                                }
                            }
                            .buttonStyle(.plain)
                        }
                        .listStyle(.plain)
                    }
                    .frame(width: 420, height: 360)
                }

                Spacer()

                Button("Снять галочки", action: store.clearSelection)
                    .disabled(store.selectedModels.isEmpty || store.isLoading)

                Button("Проверить совместимость") {
                    store.testCurrentRow()
                }
                .disabled(store.selectedRowID == nil || store.isLoading)

                Button("Сделать активной") {
                    store.selectCurrentRow()
                }
                .disabled(store.selectedRowID == nil || store.isLoading)

                Button("Включить выбранные") {
                    store.applySelection()
                }
                .buttonStyle(.borderedProminent)
                .disabled(store.selectedModels.isEmpty || store.isLoading)
            }
            .padding()
            .background(.bar)
        }
        .frame(minWidth: 1040, minHeight: 620)
        .task {
            store.loadProxyState()
            store.load()
            while !Task.isCancelled {
                store.loadPowerWatchState()
                try? await Task.sleep(nanoseconds: 5_000_000_000)
            }
        }
    }
}

@main
struct ProviderModelPickerApp: App {
    var body: some Scene {
        WindowGroup("Модели Codex") {
            ContentView()
        }
        .windowResizability(.contentMinSize)

        Settings {
            Text("Дополнительные настройки не требуются.")
                .padding()
        }
    }
}
