import SwiftUI

@MainActor
class ChatViewModel: ObservableObject {
    @Published var conversations: [ConversationResponse] = []
    @Published var currentConversation: ConversationResponse?
    @Published var messages: [ChatMessage] = []
    @Published var inputText = ""
    @Published var isStreaming = false
    @Published var isLoading = false
    @Published var error: String?
    @Published var selectedProvider: String = "gemini"
    @Published var availableProviders: [ProviderResponse] = []
    @Published var currentToolUse: String?

    private let chatService = ChatService.shared
    private var streamingContent = ""

    // MARK: - Local Message Model

    struct ChatMessage: Identifiable {
        let id: String
        let role: MessageRole
        var content: String
        let timestamp: Date
        var isStreaming: Bool

        enum MessageRole {
            case user, assistant, system
        }
    }

    // MARK: - Conversations

    func loadConversations() async {
        do {
            let response = try await chatService.listConversations(limit: 100)
            conversations = response.conversations
        } catch {
            self.error = error.localizedDescription
        }
    }

    func createConversation() async {
        do {
            let conv = try await chatService.createConversation()
            currentConversation = conv
            conversations.insert(conv, at: 0)
            messages = []
        } catch {
            self.error = error.localizedDescription
        }
    }

    func selectConversation(_ conversation: ConversationResponse) async {
        currentConversation = conversation
        await loadMessages()
    }

    func deleteConversation(_ conversation: ConversationResponse) async {
        do {
            try await chatService.deleteConversation(conversation.id)
            conversations.removeAll { $0.id == conversation.id }
            if currentConversation?.id == conversation.id {
                currentConversation = nil
                messages = []
            }
        } catch {
            self.error = error.localizedDescription
        }
    }

    func loadMessages() async {
        guard let convId = currentConversation?.id else { return }

        do {
            let serverMessages = try await chatService.getMessages(conversationId: convId)
            messages = serverMessages.map { msg in
                ChatMessage(
                    id: msg.id,
                    role: msg.role == "user" ? .user : .assistant,
                    content: msg.content,
                    timestamp: ISO8601DateFormatter().date(from: msg.createdAt) ?? Date(),
                    isStreaming: false
                )
            }
        } catch {
            self.error = error.localizedDescription
        }
    }

    // MARK: - Providers

    func loadProviders() async {
        do {
            availableProviders = try await chatService.getProviders()
            // Only set default if no provider is currently selected
            let currentValid = availableProviders.contains(where: { $0.id == selectedProvider && $0.available })
            if !currentValid, let first = availableProviders.first(where: { $0.available }) {
                selectedProvider = first.id
            }
        } catch {
            self.error = error.localizedDescription
            // Fallback: show all providers if API fails
            if availableProviders.isEmpty {
                availableProviders = [
                    ProviderResponse(id: "gemini", available: true, reason: "default"),
                    ProviderResponse(id: "claude", available: true, reason: "fallback"),
                    ProviderResponse(id: "stark_protocol", available: true, reason: "fallback"),
                ]
                selectedProvider = "gemini"
            }
        }
    }

    // MARK: - Send Message (Streaming)

    func sendMessage() async {
        let text = inputText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, !isStreaming else { return }

        inputText = ""
        isStreaming = true
        error = nil
        currentToolUse = nil

        // Add user message
        let userMsg = ChatMessage(
            id: UUID().uuidString,
            role: .user,
            content: text,
            timestamp: Date(),
            isStreaming: false
        )
        messages.append(userMsg)

        // Classify intent locally for faster routing
        let intent = await IntentDetector.shared.classify(text)

        // Check for on-device LLM preference
        let onDeviceLLM = OnDeviceLLMService.shared
        if onDeviceLLM.preferOnDevice && onDeviceLLM.state == .ready && intent.intent == "general" {
            do {
                let response = try await onDeviceLLM.generate(prompt: text, systemPrompt: "You are JARVIS, a helpful AI assistant.")
                let msg = ChatMessage(id: UUID().uuidString, role: .assistant, content: response, timestamp: Date(), isStreaming: false)
                messages.append(msg)
                isStreaming = false
                return
            } catch {
                // Fall through to backend streaming if on-device fails
            }
        }

        // Check for local music commands (handle on-device via Apple Music)
        if let musicResponse = await handleLocalMusicCommand(text) {
            let msg = ChatMessage(
                id: UUID().uuidString,
                role: .assistant,
                content: musicResponse,
                timestamp: Date(),
                isStreaming: false
            )
            messages.append(msg)
            isStreaming = false
            return
        }

        // Add placeholder for assistant
        let assistantId = UUID().uuidString
        let assistantMsg = ChatMessage(
            id: assistantId,
            role: .assistant,
            content: "",
            timestamp: Date(),
            isStreaming: true
        )
        messages.append(assistantMsg)
        streamingContent = ""

        do {
            let stream = chatService.streamMessage(
                text,
                conversationId: currentConversation?.id,
                provider: selectedProvider
            )

            for try await chunk in stream {
                switch chunk.type {
                case "start":
                    if let convId = chunk.conversationId, currentConversation == nil {
                        currentConversation = try? await chatService.getConversation(convId)
                    }

                case "token":
                    if let content = chunk.content {
                        streamingContent += content
                        if let idx = messages.lastIndex(where: { $0.id == assistantId }) {
                            messages[idx].content = streamingContent
                        }
                    }

                case "tool_call":
                    currentToolUse = chunk.tool

                case "tool_result":
                    currentToolUse = nil

                case "replace":
                    if let content = chunk.content,
                       let idx = messages.lastIndex(where: { $0.id == assistantId }) {
                        messages[idx].content = content
                        streamingContent = content
                    }

                case "end":
                    if let idx = messages.lastIndex(where: { $0.id == assistantId }) {
                        messages[idx].isStreaming = false
                    }

                case "error":
                    self.error = chunk.error ?? "Stream error"

                default:
                    break
                }
            }
        } catch {
            print("[JARVIS] Stream error: \(error)")
            self.error = error.localizedDescription
            // If stream failed, show error in the assistant message
            if let idx = messages.lastIndex(where: { $0.id == assistantId }),
               messages[idx].content.isEmpty {
                messages[idx].content = "Connection error. Please try again."
            }
        }

        if let idx = messages.lastIndex(where: { $0.id == assistantId }) {
            messages[idx].isStreaming = false
        }

        isStreaming = false
        currentToolUse = nil

        // Refresh conversation list
        await loadConversations()
    }

    // MARK: - Local Music Command Detection

    private func handleLocalMusicCommand(_ text: String) async -> String? {
        let lower = text.lowercased().trimmingCharacters(in: .whitespacesAndNewlines)

        // Music playback patterns
        let playPatterns = ["play ", "put on ", "queue up "]
        let pausePatterns = ["pause music", "pause the music", "stop music", "stop the music"]
        let skipPatterns = ["skip", "next song", "next track", "skip song"]
        let prevPatterns = ["previous song", "previous track", "go back a song", "last song"]
        let nowPlayingPatterns = ["what's playing", "what song is this", "now playing", "current song"]

        let music = MusicService.shared

        guard await music.isAuthorized else { return nil }

        for pattern in playPatterns {
            if lower.hasPrefix(pattern) {
                let query = String(lower.dropFirst(pattern.count))
                if query.isEmpty { continue }
                return try? await music.playSong(query: query)
            }
        }

        for pattern in pausePatterns {
            if lower.contains(pattern) {
                await music.pause()
                return "Music paused, sir."
            }
        }

        for pattern in skipPatterns {
            if lower.contains(pattern) {
                await music.next()
                return "Skipped to the next track."
            }
        }

        for pattern in prevPatterns {
            if lower.contains(pattern) {
                await music.previous()
                return "Back to the previous track."
            }
        }

        for pattern in nowPlayingPatterns {
            if lower.contains(pattern) {
                if let np = await music.nowPlaying() {
                    return "Currently playing: \(np.title) by \(np.artist)"
                }
                return "Nothing is currently playing."
            }
        }

        return nil // Not a music command — proceed to backend
    }
}
