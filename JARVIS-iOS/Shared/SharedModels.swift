import Foundation

// MARK: - Auth Models

struct AuthResponse: Codable {
    let accessToken: String
    let refreshToken: String
    let tokenType: String
    let user: UserResponse?
    // TOTP flow
    let needsTotp: Bool?
    let totpToken: String?

    enum CodingKeys: String, CodingKey {
        case accessToken = "access_token"
        case refreshToken = "refresh_token"
        case tokenType = "token_type"
        case user
        case needsTotp = "needs_totp"
        case totpToken = "totp_token"
    }
}

struct UserResponse: Codable, Identifiable {
    let id: String
    let email: String
    let username: String
    let fullName: String?
    let isActive: Bool
    let createdAt: String

    enum CodingKeys: String, CodingKey {
        case id, email, username
        case fullName = "full_name"
        case isActive = "is_active"
        case createdAt = "created_at"
    }
}

struct LookupResponse: Codable {
    let exists: Bool
    let userId: String?
    let username: String?
    let totpEnabled: Bool?

    enum CodingKeys: String, CodingKey {
        case exists
        case userId = "user_id"
        case username
        case totpEnabled = "totp_enabled"
    }
}

struct SetupStatusResponse: Codable {
    let setupComplete: Bool

    enum CodingKeys: String, CodingKey {
        case setupComplete = "setup_complete"
    }
}

struct UserPreferences: Codable {
    let modelPreference: String?
    let totpEnabled: Bool?

    enum CodingKeys: String, CodingKey {
        case modelPreference = "model_preference"
        case totpEnabled = "totp_enabled"
    }
}

// MARK: - Chat Models

struct ConversationResponse: Codable, Identifiable {
    let id: String
    let title: String?
    let model: String?
    let systemPrompt: String?
    let isArchived: Bool
    let messageCount: Int
    let lastMessageAt: String?
    let createdAt: String
    let updatedAt: String

    enum CodingKeys: String, CodingKey {
        case id, title, model
        case systemPrompt = "system_prompt"
        case isArchived = "is_archived"
        case messageCount = "message_count"
        case lastMessageAt = "last_message_at"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }
}

struct ConversationListResponse: Codable {
    let conversations: [ConversationResponse]
    let total: Int
}

struct MessageResponse: Codable, Identifiable {
    let id: String
    let conversationId: String
    let role: String
    let content: String
    let tokenCount: Int?
    let model: String?
    let latencyMs: Double?
    let toolCalls: String?
    let createdAt: String

    enum CodingKeys: String, CodingKey {
        case id
        case conversationId = "conversation_id"
        case role, content
        case tokenCount = "token_count"
        case model
        case latencyMs = "latency_ms"
        case toolCalls = "tool_calls"
        case createdAt = "created_at"
    }
}

struct ChatRequest: Codable {
    let message: String
    let conversationId: String?
    let model: String?
    let stream: Bool?
    let systemPrompt: String?
    let modelProvider: String?
    let voiceEnabled: Bool?

    enum CodingKeys: String, CodingKey {
        case message
        case conversationId = "conversation_id"
        case model, stream
        case systemPrompt = "system_prompt"
        case modelProvider = "model_provider"
        case voiceEnabled = "voice_enabled"
    }
}

struct CreateConversationRequest: Codable {
    let title: String?
    let model: String?
    let systemPrompt: String?

    enum CodingKeys: String, CodingKey {
        case title, model
        case systemPrompt = "system_prompt"
    }
}

struct ProviderResponse: Codable, Identifiable {
    let id: String
    let available: Bool
    let reason: String
}

// MARK: - Stream Chunk

struct StreamChunk: Codable {
    let type: String
    let content: String?
    let conversationId: String?
    let messageId: String?
    let done: Bool?
    let error: String?
    let tool: String?
    let toolArg: String?

    enum CodingKeys: String, CodingKey {
        case type, content, done, error, tool
        case conversationId = "conversation_id"
        case messageId = "message_id"
        case toolArg = "tool_arg"
    }
}

// MARK: - Voice Models

struct VoiceChatResponse: Codable {
    let transcription: String
    let responseText: String
    let audioUrl: String?
    let conversationId: String

    enum CodingKeys: String, CodingKey {
        case transcription
        case responseText = "response_text"
        case audioUrl = "audio_url"
        case conversationId = "conversation_id"
    }
}

// MARK: - Location Models

struct LocationUpdate: Codable {
    let latitude: Double
    let longitude: Double
    let city: String
    let state: String
    let country: String
}

// MARK: - Health Sync Models

struct HealthSample: Codable {
    let sampleType: String
    let value: Double
    let unit: String
    let startDate: Date
    let endDate: Date
    let sourceName: String
    var metadata: [String: String]?

    enum CodingKeys: String, CodingKey {
        case sampleType = "sample_type"
        case value, unit
        case startDate = "start_date"
        case endDate = "end_date"
        case sourceName = "source_name"
        case metadata
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(sampleType, forKey: .sampleType)
        try container.encode(value, forKey: .value)
        try container.encode(unit, forKey: .unit)
        try container.encode(ISO8601DateFormatter().string(from: startDate), forKey: .startDate)
        try container.encode(ISO8601DateFormatter().string(from: endDate), forKey: .endDate)
        try container.encode(sourceName, forKey: .sourceName)
        try container.encodeIfPresent(metadata, forKey: .metadata)
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        sampleType = try container.decode(String.self, forKey: .sampleType)
        value = try container.decode(Double.self, forKey: .value)
        unit = try container.decode(String.self, forKey: .unit)
        sourceName = try container.decode(String.self, forKey: .sourceName)
        metadata = try container.decodeIfPresent([String: String].self, forKey: .metadata)

        let formatter = ISO8601DateFormatter()
        let startStr = try container.decode(String.self, forKey: .startDate)
        let endStr = try container.decode(String.self, forKey: .endDate)
        startDate = formatter.date(from: startStr) ?? Date()
        endDate = formatter.date(from: endStr) ?? Date()
    }

    init(sampleType: String, value: Double, unit: String, startDate: Date, endDate: Date, sourceName: String, metadata: [String: String]? = nil) {
        self.sampleType = sampleType
        self.value = value
        self.unit = unit
        self.startDate = startDate
        self.endDate = endDate
        self.sourceName = sourceName
        self.metadata = metadata
    }
}

struct HealthSyncRequest: Codable {
    let samples: [HealthSample]
}

struct HealthSyncResponse: Codable {
    let inserted: Int
    let skipped: Int
    let message: String
}

// MARK: - Error

struct APIError: Codable {
    let detail: String
}
