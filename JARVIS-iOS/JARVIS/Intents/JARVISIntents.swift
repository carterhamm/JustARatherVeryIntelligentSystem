import AppIntents

// MARK: - Ask JARVIS Intent

struct AskJARVISIntent: AppIntent {
    static var title: LocalizedStringResource = "Ask JARVIS"
    static var description: IntentDescription = "Send a message to JARVIS and get a response"
    static var openAppWhenRun: Bool = true

    @Parameter(title: "Message")
    var message: String

    func perform() async throws -> some IntentResult & ProvidesDialog {
        let response = try await sendToJARVIS(message)
        return .result(dialog: "\(response)")
    }

    private func sendToJARVIS(_ text: String) async throws -> String {
        guard let url = URL(string: JARVISConfig.Chat.chat) else {
            return "JARVIS is unavailable"
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        if let token = await KeychainService.shared.load(.accessToken) {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }

        let body: [String: Any] = [
            "message": text,
            "model_provider": "gemini",
            "stream": false
        ]
        request.httpBody = try JSONSerialization.data(withJSONObject: body)

        let (data, _) = try await URLSession.shared.data(for: request)
        if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let content = json["content"] as? String {
            return content
        }
        return "I couldn't process that request, sir."
    }
}

// MARK: - Voice Mode Intent

struct VoiceModeIntent: AppIntent {
    static var title: LocalizedStringResource = "Talk to JARVIS"
    static var description: IntentDescription = "Open JARVIS voice mode"
    static var openAppWhenRun: Bool = true

    func perform() async throws -> some IntentResult {
        NotificationCenter.default.post(name: .openVoiceMode, object: nil)
        return .result()
    }
}

// MARK: - Workshop Mode Intent

struct WorkshopModeIntent: AppIntent {
    static var title: LocalizedStringResource = "Workshop Mode"
    static var description: IntentDescription = "Activate JARVIS workshop mode"
    static var openAppWhenRun: Bool = true

    func perform() async throws -> some IntentResult & ProvidesDialog {
        guard let url = URL(string: JARVISConfig.Chat.chat) else {
            return .result(dialog: "JARVIS is unavailable")
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        if let token = await KeychainService.shared.load(.accessToken) {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }

        let body: [String: Any] = [
            "message": "Wake up, daddy's home",
            "model_provider": "gemini",
            "stream": false
        ]
        request.httpBody = try JSONSerialization.data(withJSONObject: body)

        let (data, _) = try await URLSession.shared.data(for: request)
        if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let content = json["content"] as? String {
            return .result(dialog: "\(content)")
        }
        return .result(dialog: "Workshop mode activated, sir.")
    }
}

// MARK: - ATLAS Intent

struct OpenATLASIntent: AppIntent {
    static var title: LocalizedStringResource = "Open ATLAS"
    static var description: IntentDescription = "Open the JARVIS map (ATLAS)"
    static var openAppWhenRun: Bool = true

    func perform() async throws -> some IntentResult {
        NotificationCenter.default.post(name: .openAtlas, object: nil)
        return .result()
    }
}

// MARK: - Shortcuts Provider

struct JARVISShortcuts: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(
            intent: AskJARVISIntent(),
            phrases: [
                "Ask \(.applicationName) something",
                "Tell \(.applicationName) something",
                "Hey \(.applicationName)",
            ],
            shortTitle: "Ask JARVIS",
            systemImageName: "cpu"
        )
        AppShortcut(
            intent: VoiceModeIntent(),
            phrases: [
                "Talk to \(.applicationName)",
                "Open \(.applicationName) voice mode",
            ],
            shortTitle: "Voice Mode",
            systemImageName: "waveform"
        )
        AppShortcut(
            intent: WorkshopModeIntent(),
            phrases: [
                "Wake up \(.applicationName)",
                "Start \(.applicationName) workshop",
            ],
            shortTitle: "Workshop Mode",
            systemImageName: "hammer"
        )
        AppShortcut(
            intent: OpenATLASIntent(),
            phrases: [
                "Open \(.applicationName) map",
                "Show \(.applicationName) atlas",
            ],
            shortTitle: "ATLAS",
            systemImageName: "map"
        )
    }
}

// MARK: - Notification Names

extension Notification.Name {
    static let openVoiceMode = Notification.Name("openVoiceMode")
    static let openAtlas = Notification.Name("openAtlas")
}
