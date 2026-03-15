import SwiftUI

struct MessageBubbleView: View {
    let message: ChatViewModel.ChatMessage

    var isUser: Bool { message.role == .user }

    var body: some View {
        if message.content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && !message.isStreaming
            && message.role == .user {
            // Only hide empty USER messages — assistant messages may be loading
            EmptyView()
        } else {
            HStack(alignment: .top, spacing: 8) {
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

                        VStack(alignment: .leading, spacing: 0) {
                            Text(parsedContent)
                                .font(.system(size: 14, weight: .regular))
                                .foregroundColor(.jarvisText)
                                .textSelection(.enabled)
                                .lineSpacing(3)
                        }

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
                            HexCornerShape(cutSize: 10)
                                .fill(.ultraThinMaterial)
                                .overlay {
                                    HexCornerShape(cutSize: 10)
                                        .fill(Color.jarvisGold.opacity(0.06))
                                }
                                .overlay {
                                    HexCornerShape(cutSize: 10)
                                        .strokeBorder(Color.jarvisGold.opacity(0.12), lineWidth: 0.5)
                                }
                        } else {
                            HexCornerShape(cutSize: 10)
                                .fill(.ultraThinMaterial)
                                .overlay {
                                    HexCornerShape(cutSize: 10)
                                        .fill(Color.jarvisBlue.opacity(0.04))
                                }
                                .overlay {
                                    HexCornerShape(cutSize: 10)
                                        .strokeBorder(Color.jarvisBlue.opacity(0.1), lineWidth: 0.5)
                                }
                        }
                    }

                    // Timestamp
                    Text(timeString)
                        .font(.system(size: 8, design: .monospaced))
                        .foregroundColor(.jarvisTextDim.opacity(0.5))
                }
                .frame(maxWidth: UIScreen.main.bounds.width * 0.82, alignment: isUser ? .trailing : .leading)
            }
            .frame(maxWidth: .infinity, alignment: isUser ? .trailing : .leading)
        }
    }

    // MARK: - Markdown-like Attributed Content

    private var parsedContent: AttributedString {
        var text = message.content
        var result = AttributedString()

        // Process line by line for code blocks
        let lines = text.components(separatedBy: "\n")
        var inCodeBlock = false
        var codeBuffer: [String] = []

        for (i, line) in lines.enumerated() {
            if line.hasPrefix("```") {
                if inCodeBlock {
                    // End code block — render buffered code
                    let code = codeBuffer.joined(separator: "\n")
                    var codeAttr = AttributedString(code)
                    codeAttr.font = .system(size: 12, weight: .regular, design: .monospaced)
                    codeAttr.foregroundColor = Color.jarvisCyan.opacity(0.85)
                    result += codeAttr
                    codeBuffer = []
                    inCodeBlock = false
                } else {
                    inCodeBlock = true
                }
                continue
            }

            if inCodeBlock {
                codeBuffer.append(line)
                continue
            }

            // Process inline markdown
            result += parseInlineMarkdown(line)

            if i < lines.count - 1 {
                result += AttributedString("\n")
            }
        }

        // Handle unclosed code block
        if inCodeBlock && !codeBuffer.isEmpty {
            let code = codeBuffer.joined(separator: "\n")
            var codeAttr = AttributedString(code)
            codeAttr.font = .system(size: 12, weight: .regular, design: .monospaced)
            codeAttr.foregroundColor = Color.jarvisCyan.opacity(0.85)
            result += codeAttr
        }

        return result
    }

    private func parseInlineMarkdown(_ line: String) -> AttributedString {
        var result = AttributedString()
        var remaining = line[line.startIndex...]

        while !remaining.isEmpty {
            // Inline code: `code`
            if remaining.hasPrefix("`"),
               let endIdx = remaining.dropFirst().firstIndex(of: "`") {
                let codeText = String(remaining[remaining.index(after: remaining.startIndex)..<endIdx])
                var attr = AttributedString(codeText)
                attr.font = .system(size: 13, weight: .medium, design: .monospaced)
                attr.foregroundColor = Color.jarvisCyan
                result += attr
                remaining = remaining[remaining.index(after: endIdx)...]
                continue
            }

            // Bold: **text**
            if remaining.hasPrefix("**"),
               let endRange = remaining.dropFirst(2).range(of: "**") {
                let boldText = String(remaining[remaining.index(remaining.startIndex, offsetBy: 2)..<endRange.lowerBound])
                var attr = AttributedString(boldText)
                attr.font = .system(size: 14, weight: .semibold)
                result += attr
                remaining = remaining[endRange.upperBound...]
                continue
            }

            // Italic: *text*
            if remaining.hasPrefix("*"),
               !remaining.hasPrefix("**"),
               let endIdx = remaining.dropFirst().firstIndex(of: "*") {
                let italicText = String(remaining[remaining.index(after: remaining.startIndex)..<endIdx])
                var attr = AttributedString(italicText)
                attr.font = .system(size: 14).italic()
                result += attr
                remaining = remaining[remaining.index(after: endIdx)...]
                continue
            }

            // Regular character
            let ch = remaining[remaining.startIndex]
            result += AttributedString(String(ch))
            remaining = remaining[remaining.index(after: remaining.startIndex)...]
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
        formatter.dateFormat = "h:mm a"
        return formatter.string(from: message.timestamp)
    }
}
