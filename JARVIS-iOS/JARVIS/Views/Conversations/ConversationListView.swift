import SwiftUI

struct ConversationListView: View {
    @Binding var isShowing: Bool
    @EnvironmentObject var chatVM: ChatViewModel
    @State private var searchText = ""

    private var filteredConversations: [ConversationResponse] {
        if searchText.isEmpty { return chatVM.conversations }
        return chatVM.conversations.filter {
            ($0.title ?? "").localizedCaseInsensitiveContains(searchText)
        }
    }

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
                        isShowing = false
                    } label: {
                        Image(systemName: "xmark")
                            .font(.system(size: 12, weight: .medium))
                            .foregroundColor(.jarvisBlue.opacity(0.5))
                    }
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 14)

                Rectangle()
                    .fill(Color.jarvisBlue.opacity(0.1))
                    .frame(height: 0.5)

                // Search
                HStack(spacing: 8) {
                    Image(systemName: "magnifyingglass")
                        .font(.system(size: 11))
                        .foregroundColor(.jarvisBlue.opacity(0.3))

                    TextField("", text: $searchText, prompt: Text("Search conversations").foregroundColor(.jarvisTextDim.opacity(0.4)))
                        .font(.system(size: 12, design: .monospaced))
                        .foregroundColor(.jarvisText)
                        .tint(.jarvisBlue)
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(Color.jarvisBlue.opacity(0.03))

                Rectangle()
                    .fill(Color.jarvisBlue.opacity(0.06))
                    .frame(height: 0.5)

                // Conversation List
                ScrollView {
                    LazyVStack(spacing: 2) {
                        // New conversation button
                        Button {
                            Task {
                                await chatVM.createConversation()
                                isShowing = false
                            }
                        } label: {
                            HStack(spacing: 8) {
                                Image(systemName: "plus.circle")
                                    .font(.system(size: 14))
                                    .foregroundColor(.jarvisBlue.opacity(0.6))

                                Text("NEW CONVERSATION")
                                    .font(.system(size: 10, weight: .medium, design: .monospaced))
                                    .tracking(1)
                                    .foregroundColor(.jarvisBlue.opacity(0.6))

                                Spacer()
                            }
                            .padding(.horizontal, 16)
                            .padding(.vertical, 10)
                        }

                        Rectangle()
                            .fill(Color.jarvisBlue.opacity(0.06))
                            .frame(height: 0.5)
                            .padding(.horizontal, 16)

                        ForEach(filteredConversations) { conv in
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
                HexCornerShape(cutSize: 6)
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
