import Foundation

actor ChatService {
    static let shared = ChatService()

    private let api = APIClient.shared

    // MARK: - Conversations

    func listConversations(skip: Int = 0, limit: Int = 20) async throws -> ConversationListResponse {
        try await api.request("\(JARVISConfig.Chat.conversations)?skip=\(skip)&limit=\(limit)")
    }

    func createConversation(title: String? = nil) async throws -> ConversationResponse {
        try await api.request(
            JARVISConfig.Chat.conversations,
            method: "POST",
            body: CreateConversationRequest(title: title, model: nil, systemPrompt: nil)
        )
    }

    func getConversation(_ id: String) async throws -> ConversationResponse {
        try await api.request(JARVISConfig.Chat.conversation(id))
    }

    func deleteConversation(_ id: String) async throws {
        try await api.requestVoid(JARVISConfig.Chat.conversation(id), method: "DELETE")
    }

    // MARK: - Messages

    func getMessages(conversationId: String, skip: Int = 0, limit: Int = 50) async throws -> [MessageResponse] {
        try await api.request(
            "\(JARVISConfig.Chat.messages(conversationId))?skip=\(skip)&limit=\(limit)"
        )
    }

    // MARK: - Chat (Non-Streaming)

    func sendMessage(
        _ message: String,
        conversationId: String? = nil,
        provider: String? = nil
    ) async throws -> MessageResponse {
        let request = ChatRequest(
            message: message,
            conversationId: conversationId,
            model: nil,
            stream: false,
            systemPrompt: nil,
            modelProvider: provider,
            voiceEnabled: false
        )
        return try await api.request(JARVISConfig.Chat.chat, method: "POST", body: request)
    }

    // MARK: - Chat (Streaming via SSE)

    nonisolated func streamMessage(
        _ message: String,
        conversationId: String? = nil,
        provider: String? = nil
    ) -> AsyncThrowingStream<StreamChunk, Error> {
        let request = ChatRequest(
            message: message,
            conversationId: conversationId,
            model: nil,
            stream: true,
            systemPrompt: nil,
            modelProvider: provider,
            voiceEnabled: false
        )
        return api.streamRequest(JARVISConfig.Chat.stream, body: request)
    }

    // MARK: - Providers

    func getProviders() async throws -> [ProviderResponse] {
        try await api.request(JARVISConfig.Chat.providers)
    }
}
