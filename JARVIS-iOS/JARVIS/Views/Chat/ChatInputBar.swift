import SwiftUI

struct ChatInputBar: View {
    @EnvironmentObject var chatVM: ChatViewModel
    @FocusState private var isFocused: Bool
    @State private var borderGlow = false

    var body: some View {
        VStack(spacing: 0) {
            // Divider line
            Rectangle()
                .fill(
                    LinearGradient(
                        colors: [
                            .clear,
                            Color.jarvisBlue.opacity(0.15),
                            .clear
                        ],
                        startPoint: .leading,
                        endPoint: .trailing
                    )
                )
                .frame(height: 0.5)

            HStack(spacing: 10) {
                // Text input
                HStack(spacing: 8) {
                    Image(systemName: "chevron.right")
                        .font(.system(size: 10, weight: .bold, design: .monospaced))
                        .foregroundColor(.jarvisBlue.opacity(isFocused ? 0.5 : 0.2))

                    TextField("Message JARVIS...", text: $chatVM.inputText, axis: .vertical)
                        .font(.system(size: 14))
                        .foregroundColor(.jarvisText)
                        .tint(.jarvisBlue)
                        .lineLimit(1...5)
                        .focused($isFocused)
                        .onSubmit {
                            if !chatVM.inputText.isEmpty {
                                Task { await chatVM.sendMessage() }
                            }
                        }
                }
                .padding(.horizontal, 14)
                .padding(.vertical, 10)
                .background {
                    RoundedRectangle(cornerRadius: 20)
                        .fill(.ultraThinMaterial)
                        .overlay {
                            RoundedRectangle(cornerRadius: 20)
                                .fill(Color.jarvisPanelBg.opacity(0.5))
                        }
                        .overlay {
                            RoundedRectangle(cornerRadius: 20)
                                .strokeBorder(
                                    isFocused
                                        ? Color.jarvisBlue.opacity(0.3)
                                        : Color.jarvisGlassBorder,
                                    lineWidth: 0.5
                                )
                        }
                }

                // Send button
                Button {
                    Task { await chatVM.sendMessage() }
                } label: {
                    ZStack {
                        Circle()
                            .fill(canSend ? Color.jarvisBlue.opacity(0.15) : Color.clear)
                            .overlay {
                                Circle()
                                    .strokeBorder(
                                        canSend
                                            ? Color.jarvisBlue.opacity(0.4)
                                            : Color.jarvisBlue.opacity(0.1),
                                        lineWidth: 1
                                    )
                            }

                        if chatVM.isStreaming {
                            ProgressView()
                                .tint(.jarvisBlue)
                                .scaleEffect(0.7)
                        } else {
                            Image(systemName: "arrow.up")
                                .font(.system(size: 14, weight: .semibold))
                                .foregroundColor(
                                    canSend ? .jarvisBlue : .jarvisBlue.opacity(0.3)
                                )
                        }
                    }
                    .frame(width: 36, height: 36)
                    .animation(.easeInOut(duration: 0.2), value: canSend)
                }
                .disabled(!canSend)
                .cyanGlow(radius: canSend ? 8 : 0, opacity: canSend ? 0.2 : 0)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
        }
        .background {
            Rectangle()
                .fill(.ultraThinMaterial)
                .overlay {
                    Rectangle()
                        .fill(Color.jarvisDeepDark.opacity(0.7))
                }
                .ignoresSafeArea(edges: .bottom)
        }
    }

    private var canSend: Bool {
        !chatVM.inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && !chatVM.isStreaming
    }
}
