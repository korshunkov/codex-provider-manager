
import SwiftUI

struct ModelRow: Identifiable, Codable, Hashable {
    private let modelIdentifier: String
    let displayName: String
    let modelDescription: String
    let contextWindow: Int
    let inputPrice: Double?
    let outputPrice: Double?
    let pricesAreEstimated: Bool
    let metadataStatus: String
    let loadWarning: String?
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
        case metadataStatus = "metadata_status"
        case loadWarning = "load_warning"
        case intelligenceIndex = "intelligence_index"
        case codingIndex = "coding_index"
        case agenticIndex = "agentic_index"
        case providerID
        case providerName
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

    var metadataHelp: String {
        switch metadataStatus {
        case "provider":
            return "Основные данные модели получены от провайдера."
        case "reference":
            return "Часть данных получена из однозначного совпадения в OpenRouter. Цена осталась от провайдера."
        default:
            let warning = loadWarning.map { " Ошибка загрузки: \($0)" } ?? ""
            return "Контекст и/или уровни рассуждений не подтверждены. Используются безопасные значения.\(warning)"
        }
    }

    static func price(_ value: Double?, estimated: Bool = false) -> String {
        guard let value else { return "—" }
        if value == 0 { return "бесплатно" }
        return (estimated ? "~" : "") + String(format: "$%.3f", value)
    }

    init(
        modelIdentifier: String,
        displayName: String,
        modelDescription: String,
        contextWindow: Int,
        inputPrice: Double?,
        outputPrice: Double?,
        pricesAreEstimated: Bool,
        metadataStatus: String,
        loadWarning: String?,
        intelligenceIndex: Double?,
        codingIndex: Double?,
        agenticIndex: Double?,
        providerID: String? = nil,
        providerName: String? = nil
    ) {
        self.modelIdentifier = modelIdentifier
        self.displayName = displayName
        self.modelDescription = modelDescription
        self.contextWindow = contextWindow
        self.inputPrice = inputPrice
        self.outputPrice = outputPrice
        self.pricesAreEstimated = pricesAreEstimated
        self.metadataStatus = metadataStatus
        self.loadWarning = loadWarning
        self.intelligenceIndex = intelligenceIndex
        self.codingIndex = codingIndex
        self.agenticIndex = agenticIndex
        self.providerID = providerID
        self.providerName = providerName
    }
}

struct CachedModelRow: Codable {
    let modelID: String
    let displayName: String
    let modelDescription: String
    let contextWindow: Int
    let inputPrice: Double?
    let outputPrice: Double?
    let pricesAreEstimated: Bool
    let metadataStatus: String
    let loadWarning: String?
    let intelligenceIndex: Double?
    let codingIndex: Double?
    let agenticIndex: Double?
    let providerID: String
    let providerName: String?

    enum CodingKeys: String, CodingKey {
        case modelID = "model_id"
        case displayName = "display_name"
        case modelDescription = "description"
        case contextWindow = "context_window"
        case inputPrice = "input_price_per_million"
        case outputPrice = "output_price_per_million"
        case pricesAreEstimated = "price_is_estimate"
        case metadataStatus = "metadata_status"
        case loadWarning = "load_warning"
        case intelligenceIndex = "intelligence_index"
        case codingIndex = "coding_index"
        case agenticIndex = "agentic_index"
        case providerID = "provider_id"
        case providerName = "provider_name"
    }

    init(row: ModelRow) {
        modelID = row.modelID
        displayName = row.displayName
        modelDescription = row.modelDescription
        contextWindow = row.contextWindow
        inputPrice = row.inputPrice
        outputPrice = row.outputPrice
        pricesAreEstimated = row.pricesAreEstimated
        metadataStatus = row.metadataStatus
        loadWarning = row.loadWarning
        intelligenceIndex = row.intelligenceIndex
        codingIndex = row.codingIndex
        agenticIndex = row.agenticIndex
        providerID = row.providerID ?? "single"
        providerName = row.providerName
    }

    var modelRow: ModelRow {
        ModelRow(
            modelIdentifier: modelID,
            displayName: displayName,
            modelDescription: modelDescription,
            contextWindow: contextWindow,
            inputPrice: inputPrice,
            outputPrice: outputPrice,
            pricesAreEstimated: pricesAreEstimated,
            metadataStatus: metadataStatus,
            loadWarning: loadWarning,
            intelligenceIndex: intelligenceIndex,
            codingIndex: codingIndex,
            agenticIndex: agenticIndex,
            providerID: providerID,
            providerName: providerName
        )
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

struct ModelTestMetrics: Codable, Hashable {
    let latencyMs: Int
    let totalMs: Int
    let outputTokens: Int
    let tps: Double

    enum CodingKeys: String, CodingKey {
        case latencyMs = "latency_ms"
        case totalMs = "total_ms"
        case outputTokens = "output_tokens"
        case tps
    }

    var latencyText: String {
        String(format: "%.1f", Double(latencyMs) / 1000)
    }

    var tpsText: String {
        String(format: "%.0f", tps)
    }
}

struct ModelTestResponse: Decodable {
    let ok: Bool
    let message: String
    let attempts: Int?
    let metrics: ModelTestMetrics?
}

extension RowTestState {
    var errorMessage: String {
        if case .error(let message) = self { return message }
        return ""
    }
}

enum RowTestState: Equatable, Codable {
    case idle
    case loading
    case success
    case error(String)
}

struct ProviderConfig: Codable, Identifiable, Hashable {
    let id: String
    let label: String
    let baseURL: String
    let modelsURL: String?
    let apiMode: String?
    let alias: String
    let builtIn: Bool
    let hasKey: Bool

    enum CodingKeys: String, CodingKey {
        case id, label, alias
        case baseURL = "base_url"
        case modelsURL = "models_url"
        case apiMode = "api_mode"
        case builtIn = "built_in"
        case hasKey = "has_key"
    }
}

struct ProviderSettingsResponse: Decodable {
    let providers: [ProviderConfig]
    let autoCompactMode: String
    let autoCompactPercent: Int
    let autoCompactTokens: Int

    enum CodingKeys: String, CodingKey {
        case providers
        case autoCompactMode = "auto_compact_mode"
        case autoCompactPercent = "auto_compact_percent"
        case autoCompactTokens = "auto_compact_tokens"
    }
}

struct UICacheFile: Codable {
    var version = 3
    var lists: [String: [CachedModelRow]] = [:]
    var tests: [String: RowTestState] = [:]
    var metrics: [String: ModelTestMetrics] = [:]
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

struct ZCodeApplyResponse: Decodable {
    let providerID: String
    let models: [String]

    enum CodingKeys: String, CodingKey {
        case providerID = "provider_id"
        case models
    }
}

struct MavisApplyResponse: Decodable {
    let providerID: String
    let models: [String]

    enum CodingKeys: String, CodingKey {
        case providerID = "provider_id"
        case models
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
    case free

    var id: String { rawValue }
    var title: String {
        switch self {
        case .all: "Все модели"
        case .selected: "Выбранные"
        case .free: "Бесплатные"
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
    @Published var providerSettings: [ProviderConfig] = []
    @Published var autoCompactMode = "percent"
    @Published var autoCompactValue = "75"
    @Published var settingsStatus = ""
    @Published var isSettingsBusy = false
    @Published var rowTests: [String: RowTestState] = [:]
    @Published var rowMetrics: [String: ModelTestMetrics] = [:]
    @Published var keyProviderID: String?
    @Published var visibleProviderKeys: [String: String] = [:]

    var providers: [ProviderOption] {
        [ProviderOption(id: "all", name: "Все провайдеры")] +
        providerSettings.map { ProviderOption(id: $0.id, name: $0.label) }
    }

    private var allProviderIDs: [String] {
        providerSettings.map(\.id)
    }

    private let cliURL = FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent(".codex/bin/codex-provider")
    private let uiCacheURL = FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent(".codex/provider-ui-cache.json")
    var hasCachedList: Bool { !(uiCache.lists[providerID] ?? []).isEmpty }
    private var uiCache = UICacheFile()
    private let powerWatchURL = FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent(".codex/bin/codex-power-watch")

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

    func startProxyForLaunch() {
        DispatchQueue.global(qos: .utility).async { [weak self] in
            let result = Self.runProcess(self?.cliURL, arguments: ["proxy", "start", "--refresh"])
            if case .failure(.message(let error)) = result {
                DispatchQueue.main.async {
                    self?.status = "Прокси недоступен: \(error)"
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

    func loadProviderSettings(completion: (() -> Void)? = nil) {
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            let result = Self.runProcess(self?.cliURL, arguments: ["provider-settings"])
            DispatchQueue.main.async {
                guard let self else { return }
                switch result {
                case .success(let output):
                    do {
                        let settings = try JSONDecoder().decode(ProviderSettingsResponse.self, from: output)
                        self.providerSettings = settings.providers
                        self.autoCompactMode = settings.autoCompactMode
                        self.autoCompactValue = settings.autoCompactMode == "tokens"
                            ? String(settings.autoCompactTokens)
                            : String(settings.autoCompactPercent)
                    } catch {
                        self.settingsStatus = "Не удалось прочитать настройки: \(error.localizedDescription)"
                    }
                case .failure(.message(let error)):
                    self.settingsStatus = error
                }
                completion?()
            }
        }
    }

    func restoreCachedList(for newProviderID: String) {
        providerID = newProviderID
        let cachedRows = uiCache.lists[newProviderID] ?? []
        guard !cachedRows.isEmpty else {
            self.rows = []
            uiCache.lists[newProviderID] = nil
            status = "Сохранённого списка нет. Загружаю модели…"
            load()
            return
        }
        self.rows = cachedRows.map(\.modelRow)
        status = "Показан сохранённый список: \(rows.count) моделей."
    }

    func loadProviderKey(_ provider: ProviderConfig) {
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            let result = Self.runProcess(self?.cliURL, arguments: ["provider-key-show", provider.id])
            DispatchQueue.main.async {
                guard let self else { return }
                switch result {
                case .success(let output):
                    struct KeyResponse: Decodable {
                        let key: String
                    }
                    do {
                        let decoded = try JSONDecoder().decode(KeyResponse.self, from: output)
                        self.visibleProviderKeys[provider.id] = decoded.key
                    } catch {
                        self.visibleProviderKeys[provider.id] = nil
                        self.settingsStatus = "Не удалось прочитать ключ: \(error.localizedDescription)"
                    }
                case .failure(.message(let error)):
                    self.visibleProviderKeys[provider.id] = nil
                    self.settingsStatus = error
                }
            }
        }
    }

    func saveAutoCompact() {
        guard !isSettingsBusy else { return }
        let mode = autoCompactMode
        guard let value = Int(autoCompactValue), (4096...10_000_000).contains(value) else {
            settingsStatus = "Введите число: процент 10–100 или токены от 4096."
            return
        }
        isSettingsBusy = true
        settingsStatus = "Сохраняю уровень автокомпакта…"
        let arguments = ["set-auto-compact", "--mode", mode, "--value", String(value)]
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            let result = Self.runProcess(self?.cliURL, arguments: arguments)
            DispatchQueue.main.async {
                guard let self else { return }
                switch result {
                case .success:
                    self.settingsStatus = "Уровень автокомпакта сохранён."
                    self.applyCatalogConfiguration()
                case .failure(.message(let error)):
                    self.isSettingsBusy = false
                    self.settingsStatus = error
                }
            }
        }
    }

    func selectCompactionModel(_ row: ModelRow) {
        compactionModel = selection(for: row)
        applyCatalogConfiguration()
    }

    func addProvider(label: String, prefix: String, baseURL: String, modelsURL: String, apiMode: String, apiKey: String) {
        guard !isSettingsBusy else { return }
        guard !label.trimmingCharacters(in: .whitespaces).isEmpty else {
            settingsStatus = "Введите название провайдера."
            return
        }
        guard !apiKey.trimmingCharacters(in: .whitespaces).isEmpty else {
            settingsStatus = "Введите ключ провайдера."
            return
        }
        isSettingsBusy = true
        settingsStatus = "Проверяю список моделей…"
        let arguments = [
            "provider-add", "--label", label, "--prefix", prefix,
            "--base-url", baseURL, "--models-url", modelsURL,
            "--api-mode", apiMode, "--api-key-stdin",
        ]
        let keyData = apiKey.data(using: .utf8)
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            let result = Self.runProcess(self?.cliURL, arguments: arguments, stdin: keyData)
            DispatchQueue.main.async {
                guard let self else { return }
                self.isSettingsBusy = false
                switch result {
                case .success(let output):
                    self.settingsStatus = String(data: output, encoding: .utf8) ?? "Провайдер добавлен."
                    self.loadProviderSettings {
                        self.load(refresh: true)
                    }
                case .failure(.message(let error)):
                    self.settingsStatus = error
                }
            }
        }
    }

    func saveProviderKey(provider: ProviderConfig, apiKey: String) {
        guard !isSettingsBusy, !apiKey.trimmingCharacters(in: .whitespaces).isEmpty else {
            settingsStatus = "Введите ключ провайдера."
            return
        }
        isSettingsBusy = true
        settingsStatus = "Сохраняю ключ…"
        let data = apiKey.data(using: .utf8)
        let arguments = ["provider-key", provider.id, "--stdin"]
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            let result = Self.runProcess(self?.cliURL, arguments: arguments, stdin: data)
            DispatchQueue.main.async {
                guard let self else { return }
                self.isSettingsBusy = false
                switch result {
                case .success(let output):
                    self.settingsStatus = String(data: output, encoding: .utf8) ?? "Ключ сохранён."
                    self.keyProviderID = nil
                    self.loadProviderSettings()
                case .failure(.message(let error)):
                    self.settingsStatus = error
                }
            }
        }
    }

    func removeProvider(_ provider: ProviderConfig) {
        guard !isSettingsBusy, !provider.builtIn else { return }
        isSettingsBusy = true
        settingsStatus = "Удаляю провайдера…"
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            let result = Self.runProcess(self?.cliURL, arguments: ["provider-remove", provider.id])
            DispatchQueue.main.async {
                guard let self else { return }
                self.isSettingsBusy = false
                switch result {
                case .success(let output):
                    self.settingsStatus = String(data: output, encoding: .utf8) ?? "Провайдер удалён."
                    self.loadProviderSettings()
                case .failure(.message(let error)):
                    self.settingsStatus = error
                }
            }
        }
    }

    func restoreUICache() {
        guard let data = try? Data(contentsOf: uiCacheURL),
              let cache = try? JSONDecoder().decode(UICacheFile.self, from: data) else {
            status = "Сохранённого списка нет. Загружаю модели…"
            return
        }
        uiCache = cache
        let cachedRows = cache.lists[providerID] ?? []
        guard !cachedRows.isEmpty else {
            uiCache.lists[providerID] = nil
            status = "Сохранённого списка нет. Загружаю модели…"
            return
        }
        let rows = cachedRows.map(\.modelRow)
        self.rows = rows
        status = "Показан сохранённый список: \(rows.count) моделей."
        for (key, state) in cache.tests where state != .loading {
            rowTests[key] = state
        }
        for (key, metrics) in cache.metrics where cache.tests[key] == .success {
            rowMetrics[key] = metrics
        }
    }

    private func persistUICache() {
        uiCache.lists[providerID] = rows.map(CachedModelRow.init)
        uiCache.tests = rowTests.filter { $0.value != .loading }
        uiCache.metrics = rowMetrics.filter { rowTests[$0.key] == .success }
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        guard let data = try? encoder.encode(uiCache) else { return }
        let url = uiCacheURL
        DispatchQueue.global(qos: .utility).async {
            try? data.write(to: url, options: .atomic)
        }
    }

    func testRow(_ row: ModelRow, force: Bool = false) {
        let rowID = row.id
        if !force, case .error = rowTests[rowID] {
            let message = rowTests[rowID]?.errorMessage ?? ""
            NSPasteboard.general.clearContents()
            NSPasteboard.general.setString(message, forType: .string)
            status = "Текст ошибки скопирован."
            return
        }
        guard rowTests[rowID] != .loading else { return }
        let provider = row.providerID ?? providerID
        rowTests[rowID] = .loading
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            let result = Self.runProcess(self?.cliURL, arguments: ["test-model", provider, "--model", row.modelID])
            DispatchQueue.main.async {
                guard let self else { return }
                switch result {
                case .success(let output):
                    do {
                        let decoded = try JSONDecoder().decode(ModelTestResponse.self, from: output)
                        self.rowTests[rowID] = decoded.ok
                            ? .success
                            : .error(decoded.message)
                        if decoded.ok, let metrics = decoded.metrics {
                            self.rowMetrics[rowID] = metrics
                        } else if !decoded.ok {
                            self.rowMetrics.removeValue(forKey: rowID)
                        }
                        self.persistUICache()
                    } catch {
                        self.rowTests[rowID] = .error("Непонятный ответ проверки: \(error.localizedDescription)")
                        self.persistUICache()
                    }
                case .failure(.message(let error)):
                    self.rowTests[rowID] = .error(error)
                    self.persistUICache()
                }
            }
        }
    }

    func clearSelections(keys: Set<String>) {
        selectedModels.removeAll { keys.contains($0.key) }
        status = "Галочки сняты у моделей в текущем списке. Нажмите «Включить выбранные»."
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
                        self.persistUICache()
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
                    self.persistUICache()
                } else {
                    let names = failures.joined(separator: "; ")
                    self.status = "Все провайдеры: \(self.rows.count) моделей. Не загружены: \(names)."
                    self.persistUICache()
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

    /// Путь модели на локальном прокси без хоста и порта, например `or/gpt-5.2`.
    func proxyRoute(for row: ModelRow) -> String {
        guard let providerID = row.providerID,
              let provider = providerSettings.first(where: { $0.id == providerID }) else {
            return row.modelID
        }
        if providerID == "anymodel" && row.modelID.hasPrefix("am/") {
            return row.modelID
        }
        return "\(provider.alias)/\(row.modelID)"
    }

    func copyProxyRoute(_ row: ModelRow) {
        let route = proxyRoute(for: row)
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(route, forType: .string)
        status = "Скопировано: \(route)"
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

    private var autoCompactPayload: [String: Any] {
        let value = Int(autoCompactValue) ?? (autoCompactMode == "tokens" ? 200_000 : 75)
        return ["mode": autoCompactMode, "value": value]
    }

    func applyCatalogConfiguration() {
        guard !isLoading else { return }
        isLoading = true
        settingsStatus = "Применяю настройки каталога…"
        var payload: [String: Any] = [
            "models": selectedModels.map { ["provider_id": $0.providerID, "model_id": $0.modelID] },
            "auto_compact": autoCompactPayload,
        ]
        if let compactionModel {
            payload["compaction_model"] = [
                "provider_id": compactionModel.providerID,
                "model_id": compactionModel.modelID,
            ]
        } else {
            payload["compaction_model"] = NSNull()
        }
        let data: Data
        do {
            data = try JSONSerialization.data(withJSONObject: payload)
        } catch {
            isLoading = false
            settingsStatus = "Не удалось создать запрос: \(error.localizedDescription)"
            return
        }
        let arguments = ["proxy", "configure", "--stdin"]
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            let result = Self.runProcess(self?.cliURL, arguments: arguments, stdin: data)
            DispatchQueue.main.async {
                guard let self else { return }
                self.isLoading = false
                switch result {
                case .success(let output):
                    do {
                        _ = try JSONDecoder().decode(ProxyApplyResponse.self, from: output)
                        self.settingsStatus = "Настройки применены."
                        self.loadProxyState()
                    } catch {
                        self.settingsStatus = "Не удалось разобрать ответ прокси: \(error.localizedDescription)"
                    }
                case .failure(.message(let error)):
                    self.settingsStatus = error
                }
            }
        }
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
        payload["auto_compact"] = autoCompactPayload
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

    func configureZCode() {
        guard !selectedModels.isEmpty, !isLoading else { return }
        isLoading = true
        status = "Обновляю список моделей в ZCode…"
        let active = selectedRow.flatMap { selection(for: $0) }
        var payload: [String: Any] = [
            "models": selectedModels.map { ["provider_id": $0.providerID, "model_id": $0.modelID] },
        ]
        payload["compaction_model"] = compactionModel.map { selection in
            ["provider_id": selection.providerID, "model_id": selection.modelID]
        } ?? NSNull()
        if let active {
            payload["active_model"] = [
                "provider_id": active.providerID,
                "model_id": active.modelID,
            ]
        }
        payload["auto_compact"] = autoCompactPayload

        let data: Data
        do {
            data = try JSONSerialization.data(withJSONObject: payload)
        } catch {
            isLoading = false
            status = "Не удалось создать запрос для ZCode: \(error.localizedDescription)"
            return
        }

        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            let result = Self.runProcess(self?.cliURL, arguments: ["zcode-configure", "--stdin"], stdin: data)
            DispatchQueue.main.async {
                guard let self else { return }
                self.isLoading = false
                switch result {
                case .success(let output):
                    do {
                        let decoded = try JSONDecoder().decode(ZCodeApplyResponse.self, from: output)
                        self.status = "ZCode обновлён: \(decoded.models.count) моделей. Перезапустите ZCode, если он открыт."
                        self.loadProxyState()
                    } catch {
                        self.status = "Не удалось разобрать ответ ZCode: \(error.localizedDescription)"
                    }
                case .failure(.message(let error)):
                    self.status = error
                }
            }
        }
    }

    func configureMavisCode() {
        guard !selectedModels.isEmpty, !isLoading else { return }
        isLoading = true
        status = "Обновляю список моделей в MiniMax code…"
        let active = selectedRow.flatMap { selection(for: $0) }
        var payload: [String: Any] = [
            "models": selectedModels.map { ["provider_id": $0.providerID, "model_id": $0.modelID] },
        ]
        payload["compaction_model"] = compactionModel.map { selection in
            ["provider_id": selection.providerID, "model_id": selection.modelID]
        } ?? NSNull()
        if let active {
            payload["active_model"] = [
                "provider_id": active.providerID,
                "model_id": active.modelID,
            ]
        }
        payload["auto_compact"] = autoCompactPayload

        let data: Data
        do {
            data = try JSONSerialization.data(withJSONObject: payload)
        } catch {
            isLoading = false
            status = "Не удалось создать запрос для MiniMax code: \(error.localizedDescription)"
            return
        }

        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            let result = Self.runProcess(self?.cliURL, arguments: ["mavis-configure", "--stdin"], stdin: data)
            DispatchQueue.main.async {
                guard let self else { return }
                self.isLoading = false
                switch result {
                case .success(let output):
                    do {
                        let decoded = try JSONDecoder().decode(MavisApplyResponse.self, from: output)
                        self.status = "MiniMax code обновлён: \(decoded.models.count) моделей. Перезапустите MiniMax code, если он открыт."
                        self.loadProxyState()
                    } catch {
                        self.status = "Не удалось разобрать ответ MiniMax code: \(error.localizedDescription)"
                    }
                case .failure(.message(let error)):
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
                        if decoded.ok {
                            if let metrics = decoded.metrics {
                                self.status = "Проверка пройдена: первый токен через \(metrics.latencyText) с, \(metrics.tpsText) токенов/с."
                            } else {
                                self.status = "Проверка пройдена: \(decoded.message)"
                            }
                        } else {
                            self.status = "Проверка не пройдена: \(decoded.message)"
                        }
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
    @State private var showSettings = false

    private var visibleSelectionKeys: Set<String> {
        Set(filteredRows.map { "\($0.providerID ?? "single")|\($0.modelID)" })
    }

    private var filteredRows: [ModelRow] {
        let words = searchText.split(separator: " ").map { $0.lowercased() }
        return store.rows.filter { row in
            let haystack = "\(row.displayName) \(row.modelID) \(row.modelDescription) \(row.providerName ?? "")".lowercased()
            let matchesText = words.allSatisfy { haystack.contains($0) }
            let matchesFilter: Bool
            switch priceFilter {
            case .all: matchesFilter = true
            case .selected:
                matchesFilter = store.isSelected(row)
            case .free: matchesFilter = row.inputPrice == 0 || row.outputPrice == 0
            }
            return matchesText && matchesFilter
        }.sorted(using: sortOrder)
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Picker("Сервис:", selection: $store.providerID) {
                    ForEach(store.providers) { provider in
                        Text(provider.name).tag(provider.id)
                    }
                }
                .frame(maxWidth: 240)
                .onChange(of: store.providerID) { _, newValue in
                    store.restoreCachedList(for: newValue)
                }

                Picker("", selection: $priceFilter) {
                    ForEach(PriceFilter.allCases) { filter in
                        Text(filter.title).tag(filter)
                    }
                }
                .frame(maxWidth: 150)

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
                            set: { enabled in store.setSelection(row, enabled: enabled) }
                        )
                    )
                    .labelsHidden()
                }
                .width(34)

                TableColumn("Провайдер", value: \.providerNameSort) { row in
                    Text(row.providerName ?? "—").lineLimit(2)
                }
                .width(min: 120, ideal: 150)

                TableColumn("Модель", value: \.nameSort) { row in
                    HStack(alignment: .top, spacing: 5) {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(row.displayName).lineLimit(1)
                            Button {
                                store.copyProxyRoute(row)
                            } label: {
                                Text(store.proxyRoute(for: row))
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                    .lineLimit(1)
                                    .truncationMode(.middle)
                            }
                            .buttonStyle(.borderless)
                            .help("Нажмите, чтобы скопировать путь модели")
                        }
                        Image(systemName: metadataIcon(row))
                            .font(.caption)
                            .foregroundStyle(metadataColor(row))
                            .help(row.metadataHelp)
                    }
                }
                .width(min: 220, ideal: 310)

                TableColumn("Вход $/M", value: \.inputSort) { row in
                    Text(row.inputText).monospacedDigit()
                }
                .width(min: 80, ideal: 100)

                TableColumn("Выход $/M", value: \.outputSort) { row in
                    Text(row.outputText).monospacedDigit()
                }
                .width(min: 80, ideal: 100)

                TableColumn("Индекс Codex", value: \.indexSort) { row in
                    Text(row.indexText).monospacedDigit()
                }
                .width(min: 100, ideal: 120)

                TableColumn("Выгодность", value: \.valueSort) { row in
                    Text(row.valueText)
                        .monospacedDigit()
                        .foregroundStyle(row.isTopFree ? .yellow : .primary)
                }
                .width(min: 90, ideal: 105)

                TableColumn("Контекст", value: \.contextSort) { row in
                    Text(row.contextText).monospacedDigit()
                }
                .width(min: 75, ideal: 90)

                TableColumn("Тест") { row in
                    rowTestButton(row)
                }
                .width(min: 74, ideal: 84)
            }
            .overlay(alignment: .topLeading) {
                Button {
                    store.clearSelections(keys: visibleSelectionKeys)
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .font(.callout.weight(.medium))
                }
                .buttonStyle(.borderless)
                .padding(.leading, 13)
                .padding(.top, 8)
                .help("Снять галочки только у моделей в текущем списке")
            }
            .padding(.horizontal, 8)

            HStack {
                Text(store.status)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
                Spacer()
            }
            .padding(.horizontal)
            .padding(.top, 8)

            HStack {
                Button {
                    showSettings = true
                } label: {
                    Label("Настройки", systemImage: "gearshape")
                }
                .buttonStyle(.bordered)
                .padding(.vertical, 6)

                Spacer()

                Text("Выбрано: \(store.selectedModels.count)")
                    .fontWeight(.medium)

                Button {
                    store.configureZCode()
                } label: {
                    Label("Добавить в ZCode", systemImage: "square.and.arrow.down")
                }
                .buttonStyle(.bordered)
                .padding(.vertical, 6)
                .disabled(store.selectedModels.isEmpty || store.isLoading)
                .help("Создать или обновить провайдера ZCode из всех отмеченных моделей")

                Button {
                    store.configureMavisCode()
                } label: {
                    Label("Добавить в MiniMax code", systemImage: "square.and.arrow.down.on.square")
                }
                .buttonStyle(.bordered)
                .padding(.vertical, 6)
                .disabled(store.selectedModels.isEmpty || store.isLoading)
                .help("Создать или обновить провайдер MiniMax code из всех отмеченных моделей")

                Button("Применить и перезапустить Codex") {
                    store.applySelection()
                }
                .buttonStyle(.borderedProminent)
                .disabled(store.selectedModels.isEmpty || store.isLoading)
            }
            .padding()
            .background(.bar)
        }
        .frame(minWidth: 1080, minHeight: 640)
        .sheet(isPresented: $showSettings) {
            SettingsView(store: store)
        }
        .task {
            store.restoreUICache()
            store.startProxyForLaunch()
            store.loadProxyState()
            store.loadProviderSettings {
                if !store.hasCachedList {
                    store.load(refresh: true)
                }
            }
            while !Task.isCancelled {
                store.loadPowerWatchState()
                try? await Task.sleep(nanoseconds: 5_000_000_000)
            }
        }
    }

    @ViewBuilder
    private static func successLabel(metrics: ModelTestMetrics?) -> String {
        guard let metrics else { return "OK" }
        return "OK · \(metrics.latencyText)с · \(metrics.tpsText) t/s"
    }

    private static func successTooltip(metrics: ModelTestMetrics?) -> String {
        guard let metrics else {
            return "Проверка пройдена. Нажмите, чтобы проверить снова."
        }
        let seconds = String(format: "%.1f", Double(metrics.totalMs) / 1000)
        return """
        Первый токен: \(metrics.latencyText) с. \
        Полный ответ: \(seconds) с, \(metrics.outputTokens) токенов (скорость генерации \(metrics.tpsText) т/с, \
        reasoning-токены учитываются). Нажмите, чтобы проверить снова.
        """
    }

    @ViewBuilder
    private func rowTestButton(_ row: ModelRow) -> some View {
        switch store.rowTests[row.id] {
        case .loading:
            ProgressView()
                .controlSize(.small)
        case .success:
            Button {
                store.testRow(row)
            } label: {
                Text(Self.successLabel(metrics: store.rowMetrics[row.id]))
                    .font(.system(.caption, design: .monospaced))
                    .frame(maxWidth: 130)
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
            .help(Self.successTooltip(metrics: store.rowMetrics[row.id]))
        case .error(let message):
            HStack(spacing: 4) {
                Button {
                    store.testRow(row)
                } label: {
                    Image(systemName: "info.circle.fill")
                        .foregroundStyle(.red)
                }
                .buttonStyle(.borderless)
                .help("\(message)\nНажмите, чтобы скопировать ошибку.")

                Button {
                    store.testRow(row, force: true)
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .buttonStyle(.borderless)
                .help("Повторить проверку.")
            }
        default:
            Button {
                store.testRow(row)
            } label: {
                Text("Тест").frame(maxWidth: 44)
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
        }
    }

    private func metadataIcon(_ row: ModelRow) -> String {
        switch row.metadataStatus {
        case "provider": return "checkmark.circle"
        case "reference": return "info.circle"
        default: return "exclamationmark.triangle"
        }
    }

    private func metadataColor(_ row: ModelRow) -> Color {
        switch row.metadataStatus {
        case "provider": return .secondary
        case "reference": return .blue
        default: return .yellow
        }
    }
}

struct SettingsView: View {
    @Environment(\.dismiss) private var dismiss
    @ObservedObject var store: ModelStore
    @State private var compactSearch = ""
    @State private var showProviderForm = false
    @State private var providerLabel = ""
    @State private var providerPrefix = ""
    @State private var providerURL = ""
    @State private var providerModelsURL = ""
    @State private var providerAPIMode = "responses"
    @State private var providerKey = ""
    @State private var replacementKey = ""

    private var compactChoices: [ModelRow] {
        let selected = store.selectedModels
        let selectedRows = store.rows.filter { row in
            guard let providerID = row.providerID else { return false }
            return selected.contains { $0.providerID == providerID && $0.modelID == row.modelID }
        }
        return selectedRows.isEmpty ? store.rows : selectedRows
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("Настройки")
                .font(.title2.weight(.semibold))
                .padding(.horizontal, 22)
                .padding(.top, 20)

            Form {
                Section("Провайдеры и ключи") {
                    if store.providerSettings.isEmpty {
                        Text("Загружаю провайдеров…").foregroundStyle(.secondary)
                    } else {
                        ForEach(store.providerSettings) { provider in
                            VStack(alignment: .leading, spacing: 8) {
                                HStack(alignment: .firstTextBaseline) {
                                    VStack(alignment: .leading, spacing: 2) {
                                        HStack(spacing: 6) {
                                            Text(provider.label).fontWeight(.medium)
                                            if provider.builtIn {
                                                Text("встроенный")
                                                    .font(.caption2)
                                                    .padding(.horizontal, 5)
                                                    .padding(.vertical, 1)
                                                    .background(.quaternary)
                                                    .clipShape(Capsule())
                                            }
                                            if !provider.hasKey {
                                                Text("нет ключа")
                                                    .font(.caption2)
                                                    .foregroundStyle(.orange)
                                            }
                                        }
                                        Text(provider.baseURL)
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                            .lineLimit(1)
                                    }
                                    Spacer()
                                    Button(store.visibleProviderKeys[provider.id] == nil ? "Показать" : "Скрыть") {
                                        if store.visibleProviderKeys[provider.id] == nil {
                                            store.loadProviderKey(provider)
                                        } else {
                                            store.visibleProviderKeys[provider.id] = nil
                                        }
                                    }
                                    .buttonStyle(.borderless)

                                    Button("Заменить") {
                                        store.keyProviderID = provider.id
                                        replacementKey = ""
                                    }
                                    .buttonStyle(.borderless)

                                    if !provider.builtIn {
                                        Button("Удалить") {
                                            store.removeProvider(provider)
                                        }
                                        .buttonStyle(.borderless)
                                        .foregroundStyle(.red)
                                    }
                                }

                                if let key = store.visibleProviderKeys[provider.id] {
                                    HStack {
                                        Text(key)
                                            .font(.system(.caption, design: .monospaced))
                                            .lineLimit(1)
                                            .truncationMode(.middle)
                                        Spacer()
                                        Button("Копировать") {
                                            NSPasteboard.general.clearContents()
                                            NSPasteboard.general.setString(key, forType: .string)
                                        }
                                        .buttonStyle(.borderless)
                                    }
                                }

                                if store.keyProviderID == provider.id {
                                    SecureField("Новый ключ", text: $replacementKey)
                                    HStack {
                                        Button("Сохранить новый ключ") {
                                            store.saveProviderKey(provider: provider, apiKey: replacementKey)
                                            replacementKey = ""
                                        }
                                        .disabled(store.isSettingsBusy || replacementKey.isEmpty)
                                        Button("Отмена") {
                                            store.keyProviderID = nil
                                            replacementKey = ""
                                        }
                                    }
                                }
                            }
                            .padding(.vertical, 2)
                        }
                    }
                    Divider()
                    if showProviderForm {
                        TextField("Название", text: $providerLabel)
                        TextField("Префикс, например myai", text: $providerPrefix)
                        TextField("Адрес API, например https://api.example.com/v1", text: $providerURL)
                        TextField("Адрес списка моделей (необязательно)", text: $providerModelsURL)
                        Picker("Тип API", selection: $providerAPIMode) {
                            Text("Responses").tag("responses")
                            Text("Chat Completions").tag("chat")
                        }
                        SecureField("API-ключ", text: $providerKey)
                        HStack {
                            Button("Проверить и добавить") {
                                store.addProvider(
                                    label: providerLabel,
                                    prefix: providerPrefix,
                                    baseURL: providerURL,
                                    modelsURL: providerModelsURL,
                                    apiMode: providerAPIMode,
                                    apiKey: providerKey
                                )
                                providerKey = ""
                            }
                            .disabled(store.isSettingsBusy)
                            Button("Отмена") {
                                showProviderForm = false
                            }
                        }
                    } else {
                        Button("Добавить провайдера") {
                            showProviderForm = true
                        }
                    }
                }

                Section("Автокомпакт") {
                    Picker("Режим", selection: $store.autoCompactMode) {
                        Text("Процент").tag("percent")
                        Text("Токены").tag("tokens")
                    }
                    .pickerStyle(.segmented)

                    HStack {
                        if store.autoCompactMode == "tokens" {
                            TextField("200000", text: $store.autoCompactValue)
                            Text("токенов")
                        } else {
                            Slider(value: Binding(
                                get: { Double(Int(store.autoCompactValue) ?? 75) },
                                set: { store.autoCompactValue = String(Int($0)) }
                            ), in: 10...100, step: 5)
                            Text("\(store.autoCompactValue)%")
                                .monospacedDigit()
                                .frame(width: 46)
                        }
                    }

                    Menu {
                        ForEach(compactChoices) { row in
                            Button(row.displayName) {
                                store.selectCompactionModel(row)
                            }
                        }
                    } label: {
                        Label("Модель: \(store.selectionLabel(store.compactionModel))", systemImage: "arrow.down.circle")
                            .lineLimit(1)
                    }

                    Button("Сохранить и применить") {
                        store.saveAutoCompact()
                    }
                    .disabled(store.isSettingsBusy || store.isLoading)
                    Text("Процент считается отдельно для каждой модели. Токены задают одну общую границу.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Section("Защита от сна") {
                    Toggle("Защита от сна", isOn: Binding(
                        get: { store.powerWatchRunning },
                        set: { store.setPowerWatch($0) }
                    ))
                    .toggleStyle(.switch)
                    .disabled(store.isPowerWatchBusy)
                    Text("Нужна для того, чтобы при работе агента и закрытии крышки агент продолжал работу от аккумулятора.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Text(store.powerWatchStatus)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                if !store.settingsStatus.isEmpty {
                    Text(store.settingsStatus)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            .formStyle(.grouped)
            .padding(.horizontal, 14)

            HStack {
                Spacer()
                Button("Готово") {
                    showSettingsDismiss()
                }
                .keyboardShortcut(.defaultAction)
            }
            .padding()
        }
        .frame(width: 680, height: 720)
        .onAppear {
            store.loadProviderSettings()
        }
    }

    private func showSettingsDismiss() {
        dismiss()
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
