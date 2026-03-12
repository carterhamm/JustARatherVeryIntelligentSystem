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

// MARK: - Empty State (Arc Reactor)

struct EmptyStateView: View {
    @State private var rotation1 = 0.0
    @State private var rotation2 = 0.0
    @State private var coreScale = 0.8
    @State private var opacity = 0.0

    var body: some View {
        VStack(spacing: 24) {
            Spacer()

            ZStack {
                // Outer ring 3
                Circle()
                    .stroke(Color.jarvisBlue.opacity(0.08), lineWidth: 1)
                    .frame(width: 180, height: 180)

                // Segmented ring 2
                ForEach(0..<8, id: \.self) { i in
                    ArcSegment(
                        startAngle: Double(i) * 45 + 5,
                        endAngle: Double(i) * 45 + 35
                    )
                    .stroke(Color.jarvisBlue.opacity(0.15), lineWidth: 1.5)
                    .frame(width: 150, height: 150)
                    .rotationEffect(.degrees(rotation1))
                }

                // Inner segmented ring
                ForEach(0..<6, id: \.self) { i in
                    ArcSegment(
                        startAngle: Double(i) * 60 + 10,
                        endAngle: Double(i) * 60 + 45
                    )
                    .stroke(Color.jarvisBlue.opacity(0.25), lineWidth: 1)
                    .frame(width: 100, height: 100)
                    .rotationEffect(.degrees(rotation2))
                }

                // Core glow
                Circle()
                    .fill(
                        RadialGradient(
                            colors: [
                                Color.jarvisBlue.opacity(0.4),
                                Color.jarvisBlue.opacity(0.05),
                                .clear
                            ],
                            center: .center,
                            startRadius: 5,
                            endRadius: 50
                        )
                    )
                    .frame(width: 100, height: 100)
                    .scaleEffect(coreScale)

                // Inner ring
                Circle()
                    .stroke(Color.jarvisBlue.opacity(0.3), lineWidth: 1)
                    .frame(width: 50, height: 50)

                // Core dot
                Circle()
                    .fill(Color.jarvisBlue)
                    .frame(width: 8, height: 8)
                    .shadow(color: .jarvisBlue, radius: 10)
                    .shadow(color: .jarvisBlue, radius: 20)
            }
            .opacity(opacity)

            VStack(spacing: 6) {
                Text("SYSTEMS ONLINE")
                    .font(.system(size: 10, weight: .medium, design: .monospaced))
                    .tracking(3)
                    .foregroundColor(.jarvisBlue.opacity(0.5))

                Text("How may I assist you, Sir?")
                    .font(.system(size: 15, weight: .light, design: .monospaced))
                    .foregroundColor(.jarvisBlue.opacity(0.7))
            }
            .opacity(opacity)

            // Status indicators
            HStack(spacing: 24) {
                StatusDot(label: "CORE", active: true)
                StatusDot(label: "UPLINK", active: true)
                StatusDot(label: "VOICE", active: true)
            }
            .opacity(opacity)

            Spacer()
        }
        .onAppear {
            withAnimation(.linear(duration: 30).repeatForever(autoreverses: false)) {
                rotation1 = 360
            }
            withAnimation(.linear(duration: 20).repeatForever(autoreverses: false)) {
                rotation2 = -360
            }
            withAnimation(.easeInOut(duration: 2).repeatForever(autoreverses: true)) {
                coreScale = 1.1
            }
            withAnimation(.easeOut(duration: 1)) {
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
        .glassBackground(opacity: 0.3, cornerRadius: 12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .onAppear {
            Timer.scheduledTimer(withTimeInterval: 0.5, repeats: true) { _ in
                dots = dots.count >= 3 ? "" : dots + "."
            }
        }
    }
}
