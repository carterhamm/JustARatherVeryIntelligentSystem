import SwiftUI

struct MessageBubbleView: View {
    let message: ChatViewModel.ChatMessage

    var isUser: Bool { message.role == .user }

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            if isUser { Spacer(minLength: 40) }

            VStack(alignment: isUser ? .trailing : .leading, spacing: 4) {
                // Role label
                HStack(spacing: 4) {
                    if !isUser {
                        Image(systemName: "cpu")
                            .font(.system(size: 8))
                            .foregroundColor(.jarvisBlue.opacity(0.5))
                    }

                    Text(isUser ? "YOU" : "JARVIS")
                        .font(.system(size: 8, weight: .bold, design: .monospaced))
                        .tracking(1.5)
                        .foregroundColor(
                            isUser
                                ? Color.jarvisGold.opacity(0.6)
                                : Color.jarvisBlue.opacity(0.6)
                        )

                    if isUser {
                        Image(systemName: "person.fill")
                            .font(.system(size: 8))
                            .foregroundColor(.jarvisGold.opacity(0.5))
                    }
                }

                // Content
                HStack {
                    if isUser { Spacer(minLength: 0) }

                    Text(attributedContent)
                        .font(.system(size: 14, weight: .regular))
                        .foregroundColor(.jarvisText)
                        .textSelection(.enabled)
                        .lineSpacing(3)

                    if !isUser {
                        Spacer(minLength: 0)

                        // Streaming cursor
                        if message.isStreaming {
                            Rectangle()
                                .fill(Color.jarvisBlue)
                                .frame(width: 2, height: 16)
                                .opacity(cursorOpacity)
                                .onAppear { startCursorBlink() }
                        }
                    }
                }
                .padding(.horizontal, 14)
                .padding(.vertical, 10)
                .background {
                    if isUser {
                        // User message - gold tinted glass
                        RoundedRectangle(cornerRadius: 14)
                            .fill(.ultraThinMaterial)
                            .overlay {
                                RoundedRectangle(cornerRadius: 14)
                                    .fill(Color.jarvisGold.opacity(0.06))
                            }
                            .overlay {
                                RoundedRectangle(cornerRadius: 14)
                                    .strokeBorder(Color.jarvisGold.opacity(0.12), lineWidth: 0.5)
                            }
                    } else {
                        // Assistant message - cyan tinted glass
                        RoundedRectangle(cornerRadius: 14)
                            .fill(.ultraThinMaterial)
                            .overlay {
                                RoundedRectangle(cornerRadius: 14)
                                    .fill(Color.jarvisBlue.opacity(0.04))
                            }
                            .overlay {
                                RoundedRectangle(cornerRadius: 14)
                                    .strokeBorder(Color.jarvisBlue.opacity(0.1), lineWidth: 0.5)
                            }
                    }
                }

                // Timestamp
                Text(timeString)
                    .font(.system(size: 8, design: .monospaced))
                    .foregroundColor(.jarvisTextDim.opacity(0.5))
            }

            if !isUser { Spacer(minLength: 40) }
        }
    }

    // MARK: - Attributed Content (basic markdown-like)

    private var attributedContent: AttributedString {
        let result = AttributedString(message.content)
        // Apply monospace to code blocks
        if let range = result.range(of: "`") {
            _ = range // Simple fallback
        }
        return result
    }

    // MARK: - Cursor Blink

    @State private var cursorOpacity = 1.0

    private func startCursorBlink() {
        withAnimation(.easeInOut(duration: 0.6).repeatForever(autoreverses: true)) {
            cursorOpacity = 0.2
        }
    }

    // MARK: - Time

    private var timeString: String {
        let formatter = DateFormatter()
        formatter.dateFormat = "HH:mm"
        return formatter.string(from: message.timestamp)
    }
}
