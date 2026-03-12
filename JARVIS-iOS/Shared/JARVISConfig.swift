import Foundation

enum JARVISConfig {
    static let defaultBaseURL = "https://app.malibupoint.dev"
    static let apiVersion = "v1"

    static var baseURL: String {
        UserDefaults.standard.string(forKey: "jarvis_base_url") ?? defaultBaseURL
    }

    static var apiBaseURL: String { "\(baseURL)/api/\(apiVersion)" }
    static var wsBaseURL: String {
        baseURL
            .replacingOccurrences(of: "https://", with: "wss://")
            .replacingOccurrences(of: "http://", with: "ws://")
    }

    // Endpoints
    enum Auth {
        static var setupStatus: String { "\(apiBaseURL)/auth/setup-status" }
        static var lookup: String { "\(apiBaseURL)/auth/lookup" }
        static var loginBegin: String { "\(apiBaseURL)/auth/login/begin" }
        static var loginComplete: String { "\(apiBaseURL)/auth/login/complete" }
        static var totpVerify: String { "\(apiBaseURL)/auth/login/totp-verify" }
        static var refresh: String { "\(apiBaseURL)/auth/refresh" }
        static var me: String { "\(apiBaseURL)/auth/me" }
        static var preferences: String { "\(apiBaseURL)/auth/me/preferences" }
        static var location: String { "\(apiBaseURL)/auth/me/location" }
    }

    enum Chat {
        static var providers: String { "\(apiBaseURL)/chat/providers" }
        static var conversations: String { "\(apiBaseURL)/chat/conversations" }
        static var chat: String { "\(apiBaseURL)/chat/chat" }
        static var stream: String { "\(apiBaseURL)/chat/chat/stream" }
        static func conversation(_ id: String) -> String { "\(conversations)/\(id)" }
        static func messages(_ convId: String) -> String { "\(conversations)/\(convId)/messages" }
    }

    enum Voice {
        static var transcribe: String { "\(apiBaseURL)/voice/transcribe" }
        static var synthesize: String { "\(apiBaseURL)/voice/synthesize" }
        static var voiceChat: String { "\(apiBaseURL)/voice/chat" }
        static var voices: String { "\(apiBaseURL)/voice/voices" }
        static var wsVoice: String { "\(wsBaseURL)/api/\(apiVersion)/voice/ws/voice" }
    }

    enum Health {
        static var check: String { "\(baseURL)/health" }
    }

    enum HealthSync {
        static var sync: String { "\(apiBaseURL)/health/sync" }
    }
}
