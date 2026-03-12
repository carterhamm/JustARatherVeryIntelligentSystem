import SwiftUI

struct MainView: View {
    @EnvironmentObject var authVM: AuthViewModel
    @EnvironmentObject var chatVM: ChatViewModel
    @State private var showConversations = false
    @State private var showSettings = false
    @State private var showVoiceMode = false

    var body: some View {
        ZStack {
            // Background
            Color.jarvisDeepDark.ignoresSafeArea()
            GridBackground().opacity(0.15)

            VStack(spacing: 0) {
                // Status Bar
                HUDStatusBar(
                    showConversations: $showConversations,
                    showSettings: $showSettings,
                    showVoiceMode: $showVoiceMode,
                    provider: chatVM.selectedProvider,
                    isStreaming: chatVM.isStreaming
                )

                // Chat Area
                ChatView()
                    .environmentObject(chatVM)
            }

            // Scanline overlay
            ScanlineOverlay()
                .allowsHitTesting(false)

            // Side panels
            if showConversations {
                ConversationListView(isShowing: $showConversations)
                    .environmentObject(chatVM)
                    .transition(.move(edge: .leading).combined(with: .opacity))
            }

            if showSettings {
                SettingsView(isShowing: $showSettings)
                    .environmentObject(authVM)
                    .environmentObject(chatVM)
                    .transition(.move(edge: .trailing).combined(with: .opacity))
            }

            if showVoiceMode {
                VoiceModeView(isShowing: $showVoiceMode)
                    .environmentObject(chatVM)
                    .transition(.opacity)
            }
        }
        .animation(.spring(response: 0.4, dampingFraction: 0.85), value: showConversations)
        .animation(.spring(response: 0.4, dampingFraction: 0.85), value: showSettings)
        .animation(.spring(response: 0.4, dampingFraction: 0.85), value: showVoiceMode)
        .task {
            await chatVM.loadProviders()
            await chatVM.loadConversations()
        }
    }
}

// MARK: - HUD Status Bar

struct HUDStatusBar: View {
    @Binding var showConversations: Bool
    @Binding var showSettings: Bool
    @Binding var showVoiceMode: Bool
    let provider: String
    let isStreaming: Bool

    @State private var time = ""
    private let timer = Timer.publish(every: 1, on: .main, in: .common).autoconnect()

    var body: some View {
        HStack(spacing: 0) {
            // Left: Menu + Logo
            HStack(spacing: 12) {
                Button {
                    showConversations.toggle()
                } label: {
                    Image(systemName: "line.3.horizontal")
                        .font(.system(size: 14, weight: .medium))
                        .foregroundColor(.jarvisBlue)
                }

                HStack(spacing: 6) {
                    Circle()
                        .fill(Color.jarvisOnline)
                        .frame(width: 5, height: 5)
                        .shadow(color: .jarvisOnline, radius: 4)

                    Text("JARVIS")
                        .font(.system(size: 11, weight: .semibold, design: .monospaced))
                        .tracking(2)
                        .foregroundColor(.jarvisBlue)
                }

                if isStreaming {
                    HStack(spacing: 2) {
                        ForEach(0..<4, id: \.self) { i in
                            SpectrumBar(index: i)
                        }
                    }
                }
            }

            Spacer()

            // Right: Provider + Voice + Time + Settings
            HStack(spacing: 14) {
                // Provider badge
                Text(provider.uppercased())
                    .font(.system(size: 8, weight: .bold, design: .monospaced))
                    .tracking(1)
                    .foregroundColor(.jarvisBlue.opacity(0.6))
                    .padding(.horizontal, 8)
                    .padding(.vertical, 3)
                    .background {
                        Capsule()
                            .fill(Color.jarvisBlue.opacity(0.08))
                            .overlay {
                                Capsule()
                                    .strokeBorder(Color.jarvisBlue.opacity(0.15), lineWidth: 0.5)
                            }
                    }

                // Voice button
                Button {
                    showVoiceMode = true
                } label: {
                    Image(systemName: "waveform")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(.jarvisBlue.opacity(0.7))
                }

                // Time
                Text(time)
                    .font(.system(size: 9, weight: .medium, design: .monospaced))
                    .foregroundColor(.jarvisBlue.opacity(0.5))

                // Settings
                Button {
                    showSettings.toggle()
                } label: {
                    Image(systemName: "gearshape")
                        .font(.system(size: 13))
                        .foregroundColor(.jarvisBlue.opacity(0.6))
                }
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .glassCapsule(opacity: 0.6)
        .padding(.horizontal, 8)
        .padding(.top, 4)
        .onReceive(timer) { _ in
            let formatter = DateFormatter()
            formatter.dateFormat = "HH:mm"
            time = formatter.string(from: Date())
        }
        .onAppear {
            let formatter = DateFormatter()
            formatter.dateFormat = "HH:mm"
            time = formatter.string(from: Date())
        }
    }
}

// MARK: - Spectrum Bar (Activity Indicator)

struct SpectrumBar: View {
    let index: Int
    @State private var height: CGFloat = 3

    var body: some View {
        RoundedRectangle(cornerRadius: 1)
            .fill(Color.jarvisBlue.opacity(0.6))
            .frame(width: 2, height: height)
            .onAppear {
                withAnimation(
                    .easeInOut(duration: 0.3 + Double(index) * 0.1)
                    .repeatForever(autoreverses: true)
                ) {
                    height = CGFloat.random(in: 4...12)
                }
            }
    }
}
