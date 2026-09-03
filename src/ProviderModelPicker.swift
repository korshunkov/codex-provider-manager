
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
}

struct ProviderOption: Hashable, Identifiable {
    let id: String
    let name: String
}

enum PriceFilter: String, CaseIterable, Identifiable {
    case all
    case withPrice
    case free
    case withIndex

    var id: String { rawValue }
    var title: String {
        switch self {
        case .all: "Все модели"
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

    func selectCurrentRow() {
        guard let row = selectedRow else { return }
        isLoading = true
        status = "Выбираю модель…"
        let arguments = ["use", row.providerID ?? providerID, "--model", row.modelID]

        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            let result = Self.runProcess(self?.cliURL, arguments: arguments)
            DispatchQueue.main.async {
                guard let self else { return }
                switch result {
                case .success:
                    self.status = "Модель выбрана. Перезапускаю Codex…"
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
        status = "Проверяю модель коротким запросом…"
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

    nonisolated private static func runProcess(_ executableURL: URL?, arguments: [String]) -> Result<Data, ProcessError> {
        guard let executableURL else { return .failure(.message("Не задан путь к codex-provider.")) }
        let process = Process()
        let output = Pipe()
        let errors = Pipe()
        process.executableURL = executableURL
        process.arguments = arguments
        process.standardOutput = output
        process.standardError = errors

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

    private var filteredRows: [ModelRow] {
        let words = searchText.split(separator: " ").map { $0.lowercased() }
        let rows = store.rows.filter { row in
            let haystack = "\(row.displayName) \(row.modelID) \(row.modelDescription) \(row.providerName ?? "")".lowercased()
            let matchesText = words.allSatisfy { haystack.contains($0) }
            let matchesFilter: Bool
            switch priceFilter {
            case .all: matchesFilter = true
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
                Button("Выбрать модель") {
                    store.selectCurrentRow()
                }
                .buttonStyle(.borderedProminent)
                .disabled(store.selectedRowID == nil || store.isLoading)
                Button("Проверить совместимость") {
                    store.testCurrentRow()
                }
                .disabled(store.selectedRowID == nil || store.isLoading)
            }
            .padding()
            .background(.bar)
        }
        .frame(minWidth: 940, minHeight: 580)
        .task { store.load() }
    }
}

@main
struct ProviderModelPickerApp: App {
    var body: some Scene {
        WindowGroup("Модели Codex") {
            ContentView()
        }
        .windowResizability(.contentMinSize)
    }
}
