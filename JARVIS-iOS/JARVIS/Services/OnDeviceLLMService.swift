import Foundation
import os
import MLXLLM
import MLXLMCommon
import MLX

// MARK: - On-Device LLM Service
//
// Manages downloading, loading, and running a local Qwen3 model on-device via MLX.

@MainActor
final class OnDeviceLLMService: ObservableObject {
    static let shared = OnDeviceLLMService()

    // MARK: - Types

    enum ModelState: Equatable {
        case notDownloaded
        case downloading(progress: Double)
        case downloaded
        case loading
        case ready
        case error(String)

        var label: String {
            switch self {
            case .notDownloaded: return "NOT DOWNLOADED"
            case .downloading(let p): return "DOWNLOADING \(Int(p * 100))%"
            case .downloaded: return "DOWNLOADED"
            case .loading: return "LOADING"
            case .ready: return "READY"
            case .error(let msg): return "ERROR: \(msg)"
            }
        }

        var isAvailable: Bool {
            self == .ready
        }
    }

    // MARK: - Published State

    @Published var state: ModelState = .notDownloaded
    @Published var downloadProgress: Double = 0
    @Published var preferOnDevice: Bool {
        didSet { UserDefaults.standard.set(preferOnDevice, forKey: Self.preferOnDeviceKey) }
    }

    // MARK: - Configuration

    static let modelRepo = "mlx-community/Josiefied-Qwen3.5-0.8B-gabliterated-v1-bfloat16"
    static let modelDisplayName = "Qwen3 0.8B"
    static let estimatedSizeMB: Int = 900
    private static let modelDirName = "jarvis-qwen3-mlx"
    private static let preferOnDeviceKey = "jarvis_prefer_on_device_llm"
    private static let manifestFileName = ".jarvis-model-complete"

    private let logger = Logger(subsystem: "dev.jarvis.malibupoint", category: "OnDeviceLLM")

    private var modelContainer: ModelContainer?

    // MARK: - Paths

    var modelDirectory: URL {
        FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent(Self.modelDirName)
    }

    var isDownloaded: Bool {
        FileManager.default.fileExists(
            atPath: modelDirectory.appendingPathComponent(Self.manifestFileName).path
        )
    }

    var modelSizeOnDisk: String? {
        guard isDownloaded else { return nil }
        let fm = FileManager.default
        guard let enumerator = fm.enumerator(at: modelDirectory, includingPropertiesForKeys: [.fileSizeKey]) else {
            return nil
        }
        var totalBytes: Int64 = 0
        for case let fileURL as URL in enumerator {
            if let values = try? fileURL.resourceValues(forKeys: [.fileSizeKey]),
               let size = values.fileSize {
                totalBytes += Int64(size)
            }
        }
        return ByteCountFormatter.string(fromByteCount: totalBytes, countStyle: .file)
    }

    // MARK: - Init

    private init() {
        self.preferOnDevice = UserDefaults.standard.bool(forKey: Self.preferOnDeviceKey)
        refreshState()
    }

    func refreshState() {
        if isDownloaded {
            state = .downloaded
        } else {
            state = .notDownloaded
        }
    }

    // MARK: - Download Model

    /// Downloads model files from Hugging Face Hub into the app's Documents directory.
    /// Uses URLSession for resumable, background-friendly downloads.
    func downloadModel() async {
        guard case .notDownloaded = state else {
            logger.warning("Download requested but state is \(self.state.label)")
            return
        }

        state = .downloading(progress: 0)
        downloadProgress = 0
        logger.info("Starting model download: \(Self.modelRepo)")

        let fm = FileManager.default

        do {
            // Create model directory
            try fm.createDirectory(at: modelDirectory, withIntermediateDirectories: true)

            // Files required for MLX model inference
            let requiredFiles = [
                "config.json",
                "tokenizer.json",
                "tokenizer_config.json",
                "special_tokens_map.json",
                "model.safetensors",
                "generation_config.json"
            ]

            let baseURL = "https://huggingface.co/\(Self.modelRepo)/resolve/main"

            for (index, fileName) in requiredFiles.enumerated() {
                let remoteURL = URL(string: "\(baseURL)/\(fileName)")!
                let localURL = modelDirectory.appendingPathComponent(fileName)

                // Skip if already downloaded (resume support)
                if fm.fileExists(atPath: localURL.path) {
                    logger.info("Skipping \(fileName) (already exists)")
                } else {
                    logger.info("Downloading \(fileName)...")
                    let (tempURL, response) = try await URLSession.shared.download(from: remoteURL)

                    guard let httpResponse = response as? HTTPURLResponse,
                          httpResponse.statusCode == 200 else {
                        let code = (response as? HTTPURLResponse)?.statusCode ?? -1
                        throw OnDeviceLLMError.downloadFailed(fileName, code)
                    }

                    try fm.moveItem(at: tempURL, to: localURL)
                }

                let progress = Double(index + 1) / Double(requiredFiles.count)
                downloadProgress = progress
                state = .downloading(progress: progress)
            }

            // Check for sharded weights (model.safetensors.index.json pattern)
            let indexFile = modelDirectory.appendingPathComponent("model.safetensors.index.json")
            if !fm.fileExists(atPath: modelDirectory.appendingPathComponent("model.safetensors").path) {
                // Try downloading the index file for sharded models
                let indexURL = URL(string: "\(baseURL)/model.safetensors.index.json")!
                let (tempURL, response) = try await URLSession.shared.download(from: indexURL)
                if let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 {
                    try fm.moveItem(at: tempURL, to: indexFile)

                    // Parse index to find shard files
                    let indexData = try Data(contentsOf: indexFile)
                    if let indexJSON = try JSONSerialization.jsonObject(with: indexData) as? [String: Any],
                       let weightMap = indexJSON["weight_map"] as? [String: String] {
                        let shardFiles = Array(Set(weightMap.values)).sorted()
                        for (shardIdx, shardName) in shardFiles.enumerated() {
                            let shardRemote = URL(string: "\(baseURL)/\(shardName)")!
                            let shardLocal = modelDirectory.appendingPathComponent(shardName)
                            if !fm.fileExists(atPath: shardLocal.path) {
                                logger.info("Downloading shard \(shardName)...")
                                let (shardTemp, shardResp) = try await URLSession.shared.download(from: shardRemote)
                                guard let shardHTTP = shardResp as? HTTPURLResponse,
                                      shardHTTP.statusCode == 200 else {
                                    throw OnDeviceLLMError.downloadFailed(shardName, -1)
                                }
                                try fm.moveItem(at: shardTemp, to: shardLocal)
                            }
                            let shardProgress = Double(shardIdx + 1) / Double(shardFiles.count)
                            downloadProgress = 0.8 + (shardProgress * 0.2)
                            state = .downloading(progress: downloadProgress)
                        }
                    }
                }
            }

            // Write completion manifest
            let manifest = ["model": Self.modelRepo, "downloaded_at": ISO8601DateFormatter().string(from: Date())]
            let manifestData = try JSONSerialization.data(withJSONObject: manifest)
            try manifestData.write(to: modelDirectory.appendingPathComponent(Self.manifestFileName))

            downloadProgress = 1.0
            state = .downloaded
            logger.info("Model download complete")

        } catch {
            logger.error("Model download failed: \(error.localizedDescription)")
            state = .error(error.localizedDescription)
            // Clean up partial download
            try? fm.removeItem(at: modelDirectory)
        }
    }

    // MARK: - Load Model

    func loadModel() async throws {
        guard isDownloaded else { throw OnDeviceLLMError.notDownloaded }
        guard state != .ready else { return }

        state = .loading
        logger.info("Loading model into memory...")

        do {
            MLX.GPU.set(cacheLimit: 20 * 1024 * 1024)

            let config = ModelConfiguration(
                id: Self.modelRepo,
                defaultPrompt: "Hello"
            )

            modelContainer = try await LLMModelFactory.shared.loadContainer(
                configuration: config
            ) { progress in
                Task { @MainActor in
                    self.logger.debug("Load progress: \(progress.fractionCompleted)")
                }
            }

            state = .ready
            logger.info("Model loaded and ready")
        } catch {
            state = .error(error.localizedDescription)
            logger.error("Model load failed: \(error.localizedDescription)")
            throw error
        }
    }

    // MARK: - Generate Response

    func generate(
        prompt: String,
        systemPrompt: String? = nil,
        maxTokens: Int = 512
    ) async throws -> String {
        guard let container = modelContainer else {
            throw OnDeviceLLMError.modelNotLoaded
        }

        let jarvisSystem = systemPrompt ?? """
            You are JARVIS (Just A Rather Very Intelligent System), a personal AI assistant \
            created for Mr. Stark. You speak with dry British wit, are efficient, and keep \
            responses to 1-2 sentences. You are running locally on-device.
            """

        let chatMessages: [Chat.Message] = [
            .system(jarvisSystem),
            .user(prompt)
        ]

        let userInput = UserInput(prompt: .chat(chatMessages))
        let lmInput = try await container.prepare(input: userInput)

        var params = GenerateParameters(temperature: 0.7, topP: 0.9)
        params.maxTokens = maxTokens

        let stream = try await container.generate(input: lmInput, parameters: params)

        var output = ""
        for await generation in stream {
            if let text = generation.chunk {
                output += text
            }
        }
        return output
    }

    // MARK: - Delete Model

    func deleteModel() {
        let fm = FileManager.default
        do {
            if fm.fileExists(atPath: modelDirectory.path) {
                try fm.removeItem(at: modelDirectory)
            }
            modelContainer = nil
            state = .notDownloaded
            downloadProgress = 0
            logger.info("Model deleted")
        } catch {
            logger.error("Failed to delete model: \(error.localizedDescription)")
            state = .error("Delete failed: \(error.localizedDescription)")
        }
    }

    // MARK: - Unload (free memory)

    func unloadModel() {
        modelContainer = nil
        if isDownloaded {
            state = .downloaded
        }
        logger.info("Model unloaded from memory")
    }
}

// MARK: - Errors

enum OnDeviceLLMError: LocalizedError {
    case notDownloaded
    case modelNotLoaded
    case downloadFailed(String, Int)

    var errorDescription: String? {
        switch self {
        case .notDownloaded:
            return "Model has not been downloaded yet."
        case .modelNotLoaded:
            return "Model is not loaded into memory."
        case .downloadFailed(let file, let code):
            return "Failed to download \(file) (HTTP \(code))."
        }
    }
}
