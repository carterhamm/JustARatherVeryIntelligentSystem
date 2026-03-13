import SwiftUI

struct ChatView: View {
    @EnvironmentObject var chatVM: ChatViewModel

    var body: some View {
        VStack(spacing: 0) {
            if chatVM.messages.isEmpty && !chatVM.isStreaming {
                EmptyStateView()
            } else {
                // Messages
                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(spacing: 12) {
                            ForEach(chatVM.messages) { message in
                                MessageBubbleView(message: message)
                                    .id(message.id)
                            }

                            // Tool use indicator
                            if let tool = chatVM.currentToolUse {
                                ToolUseIndicator(toolName: tool)
                            }
                        }
                        .padding(.horizontal, 12)
                        .padding(.top, 12)
                        .padding(.bottom, 8)
                    }
                    .scrollDismissesKeyboard(.interactively)
                    .onChange(of: chatVM.messages.count) { _, _ in
                        if let last = chatVM.messages.last {
                            withAnimation(.easeOut(duration: 0.3)) {
                                proxy.scrollTo(last.id, anchor: .bottom)
                            }
                        }
                    }
                    .onChange(of: chatVM.messages.last?.content) { _, _ in
                        if let last = chatVM.messages.last {
                            proxy.scrollTo(last.id, anchor: .bottom)
                        }
                    }
                }
            }

            // Input
            ChatInputBar()
                .environmentObject(chatVM)
        }
    }
}

// MARK: - Empty State (3D Particle Cloud)

struct EmptyStateView: View {
    @State private var opacity = 0.0

    var body: some View {
        ZStack {
            // 3D SceneKit particle cloud
            ParticleCloudView(allowsCameraControl: true)
                .opacity(opacity * 0.85)

            // Overlay text
            VStack(spacing: 24) {
                Spacer()
                Spacer()
                Spacer()

                VStack(spacing: 6) {
                    Text("SYSTEMS ONLINE")
                        .font(.system(size: 10, weight: .medium, design: .monospaced))
                        .tracking(3)
                        .foregroundColor(.jarvisBlue.opacity(0.5))

                    Text("How may I assist you, Sir?")
                        .font(.system(size: 15, weight: .light, design: .monospaced))
                        .foregroundColor(.jarvisBlue.opacity(0.7))
                }

                // Status indicators
                HStack(spacing: 24) {
                    StatusDot(label: "CORE", active: true)
                    StatusDot(label: "UPLINK", active: true)
                    StatusDot(label: "VOICE", active: true)
                }

                Spacer()
                    .frame(height: 80)
            }
            .opacity(opacity)
        }
        .onAppear {
            withAnimation(.easeOut(duration: 1.5)) {
                opacity = 1
            }
        }
    }
}

struct StatusDot: View {
    let label: String
    let active: Bool

    var body: some View {
        HStack(spacing: 4) {
            Circle()
                .fill(active ? Color.jarvisOnline : Color.jarvisError)
                .frame(width: 4, height: 4)
                .shadow(color: active ? .jarvisOnline : .jarvisError, radius: 3)

            Text(label)
                .font(.system(size: 8, weight: .medium, design: .monospaced))
                .tracking(1)
                .foregroundColor(.jarvisTextDim)
        }
    }
}

struct ToolUseIndicator: View {
    let toolName: String
    @State private var dots = ""

    var body: some View {
        HStack(spacing: 8) {
            ProgressView()
                .tint(.jarvisBlue)
                .scaleEffect(0.7)

            Text("Using: \(toolName)\(dots)")
                .font(.system(size: 11, design: .monospaced))
                .foregroundColor(.jarvisBlue.opacity(0.7))
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 8)
        .glassBackground(opacity: 0.3, cutSize: 8)
        .frame(maxWidth: .infinity, alignment: .leading)
        .onAppear {
            Timer.scheduledTimer(withTimeInterval: 0.5, repeats: true) { _ in
                dots = dots.count >= 3 ? "" : dots + "."
            }
        }
    }
}
