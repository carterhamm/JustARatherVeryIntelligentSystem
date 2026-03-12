import SwiftUI

struct ConversationListView: View {
    @Binding var isShowing: Bool
    @EnvironmentObject var chatVM: ChatViewModel

    var body: some View {
        ZStack(alignment: .leading) {
            // Dimming background
            Color.black.opacity(0.4)
                .ignoresSafeArea()
                .onTapGesture { isShowing = false }

            // Panel
            VStack(spacing: 0) {
                // Header
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("CONVERSATIONS")
                            .font(.system(size: 10, weight: .bold, design: .monospaced))
                            .tracking(3)
                            .foregroundColor(.jarvisBlue)

                        Text("\(chatVM.conversations.count) sessions")
                            .font(.system(size: 9, design: .monospaced))
                            .foregroundColor(.jarvisTextDim)
                    }

                    Spacer()

                    Button {
                        Task {
                            await chatVM.createConversation()
                            isShowing = false
                        }
                    } label: {
                        Image(systemName: "plus")
                            .font(.system(size: 14, weight: .medium))
                            .foregroundColor(.jarvisBlue)
                            .frame(width: 32, height: 32)
                            .background {
                                Circle()
                                    .fill(Color.jarvisBlue.opacity(0.1))
                                    .overlay {
                                        Circle()
                                            .strokeBorder(Color.jarvisBlue.opacity(0.2), lineWidth: 0.5)
                                    }
                            }
                    }
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 14)

                Rectangle()
                    .fill(Color.jarvisBlue.opacity(0.1))
                    .frame(height: 0.5)

                // Conversation List
                ScrollView {
                    LazyVStack(spacing: 2) {
                        ForEach(chatVM.conversations) { conv in
                            ConversationRow(
                                conversation: conv,
                                isSelected: chatVM.currentConversation?.id == conv.id
                            )
                            .onTapGesture {
                                Task {
                                    await chatVM.selectConversation(conv)
                                    isShowing = false
                                }
                            }
                            .contextMenu {
                                Button(role: .destructive) {
                                    Task { await chatVM.deleteConversation(conv) }
                                } label: {
                                    Label("Delete", systemImage: "trash")
                                }
                            }
                        }
                    }
                    .padding(.vertical, 4)
                }
            }
            .frame(width: 300)
            .background {
                Rectangle()
                    .fill(.ultraThinMaterial)
                    .overlay {
                        Rectangle()
                            .fill(Color.jarvisDeepDark.opacity(0.85))
                    }
                    .overlay(alignment: .trailing) {
                        Rectangle()
                            .fill(Color.jarvisBlue.opacity(0.08))
                            .frame(width: 0.5)
                    }
                    .ignoresSafeArea()
            }
        }
    }
}

// MARK: - Conversation Row

struct ConversationRow: View {
    let conversation: ConversationResponse
    let isSelected: Bool

    var body: some View {
        HStack(spacing: 10) {
            // Accent bar
            RoundedRectangle(cornerRadius: 1)
                .fill(isSelected ? Color.jarvisBlue : Color.clear)
                .frame(width: 2, height: 30)

            VStack(alignment: .leading, spacing: 3) {
                Text(conversation.title ?? "New Chat")
                    .font(.system(size: 13, weight: isSelected ? .medium : .regular))
                    .foregroundColor(isSelected ? .jarvisBlue : .jarvisText)
                    .lineLimit(1)

                HStack(spacing: 6) {
                    Text("\(conversation.messageCount) msgs")
                        .font(.system(size: 9, design: .monospaced))
                        .foregroundColor(.jarvisTextDim)

                    if let lastMsg = conversation.lastMessageAt {
                        Text(formatDate(lastMsg))
                            .font(.system(size: 9, design: .monospaced))
                            .foregroundColor(.jarvisTextDim.opacity(0.6))
                    }
                }
            }

            Spacer()
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background {
            if isSelected {
                RoundedRectangle(cornerRadius: 6)
                    .fill(Color.jarvisBlue.opacity(0.06))
            }
        }
    }

    private func formatDate(_ dateStr: String) -> String {
        let iso = ISO8601DateFormatter()
        guard let date = iso.date(from: dateStr) else { return "" }
        let formatter = RelativeDateTimeFormatter()
        formatter.unitsStyle = .abbreviated
        return formatter.localizedString(for: date, relativeTo: Date())
    }
}
