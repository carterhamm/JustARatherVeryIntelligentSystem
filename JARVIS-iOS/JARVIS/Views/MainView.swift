import SwiftUI

struct MainView: View {
    @EnvironmentObject var authVM: AuthViewModel
    @EnvironmentObject var chatVM: ChatViewModel
    @State private var showConversations = false
    @State private var showSettings = false
    @State private var showVoiceMode = false
    @State private var showAtlas = false

    var body: some View {
        ZStack {
            // Background
            Color.jarvisDeepDark.ignoresSafeArea()
            GridBackground().opacity(0.15)

            // HUD frame elements
            HUDEdgeLines().ignoresSafeArea()

            // Corners
            VStack {
                HStack {
                    HUDCorner(position: .topLeft)
                    Spacer()
                    HUDCorner(position: .topRight)
                }
                Spacer()
                HStack {
                    HUDCorner(position: .bottomLeft)
                    Spacer()
                    HUDCorner(position: .bottomRight)
                }
            }
            .padding(6)
            .allowsHitTesting(false)

            VStack(spacing: 0) {
                // Status Bar
                HUDStatusBar(
                    showConversations: $showConversations,
                    showSettings: $showSettings,
                    showVoiceMode: $showVoiceMode,
                    showAtlas: $showAtlas,
                    provider: chatVM.selectedProvider,
                    isStreaming: chatVM.isStreaming
                )

                // Chat Area
                ChatView()
                    .environmentObject(chatVM)
            }

            // Vignette + Scanline overlays
            VignetteOverlay()
                .allowsHitTesting(false)
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

            if showAtlas {
                AtlasMapView(isShowing: $showAtlas)
                    .transition(.opacity)
            }
        }
        .animation(.spring(response: 0.4, dampingFraction: 0.85), value: showConversations)
        .animation(.spring(response: 0.4, dampingFraction: 0.85), value: showSettings)
        .animation(.spring(response: 0.4, dampingFraction: 0.85), value: showVoiceMode)
        .animation(.spring(response: 0.4, dampingFraction: 0.85), value: showAtlas)
        .onChange(of: showConversations) { newValue in
            if newValue { UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil) }
        }
        .onChange(of: showSettings) { newValue in
            if newValue { UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil) }
        }
        .simultaneousGesture(
            DragGesture(minimumDistance: 20, coordinateSpace: .global)
                .onEnded { value in
                    let horizontal = value.translation.width
                    let vertical = abs(value.translation.height)
                    guard abs(horizontal) > vertical * 1.5 else { return }
                    if horizontal > 50 && value.startLocation.x < 50 {
                        withAnimation { showConversations = true }
                    } else if horizontal < -50 && value.startLocation.x > UIScreen.main.bounds.width - 50 {
                        withAnimation { showSettings = true }
                    }
                }
        )
        .onReceive(NotificationCenter.default.publisher(for: .openVoiceMode)) { _ in
            showVoiceMode = true
        }
        .onReceive(NotificationCenter.default.publisher(for: .openAtlas)) { _ in
            showAtlas = true
        }
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
    @Binding var showAtlas: Bool
    let provider: String
    let isStreaming: Bool

    @State private var time = ""
    @State private var date = ""
    private let timer = Timer.publish(every: 1, on: .main, in: .common).autoconnect()

    private var status: String {
        isStreaming ? "PROCESSING" : "STANDBY"
    }

    private var providerColor: Color {
        switch provider {
        case "claude": return Color(hex: "ff8c00")
        case "gemini": return Color(hex: "4285F4")
        case "stark_protocol": return Color(hex: "39ff14")
        default: return .jarvisBlue
        }
    }

    var body: some View {
        HStack(spacing: 0) {
            // Left: Logo + Status
            HStack(spacing: 10) {
                HStack(spacing: 6) {
                    Circle()
                        .fill(isStreaming ? Color.jarvisBlue : Color.jarvisOnline)
                        .frame(width: 5, height: 5)
                        .shadow(color: isStreaming ? .jarvisBlue : .jarvisOnline, radius: 4)

                    Text("JARVIS")
                        .font(.system(size: 11, weight: .semibold, design: .monospaced))
                        .tracking(2)
                        .foregroundColor(.jarvisBlue)
                }

                // Divider
                Rectangle()
                    .fill(Color.white.opacity(0.06))
                    .frame(width: 0.5, height: 14)

                // Status label
                HStack(spacing: 4) {
                    Circle()
                        .fill(isStreaming ? Color.jarvisBlue : Color.jarvisOnline)
                        .frame(width: 4, height: 4)

                    Text(status)
                        .font(.system(size: 8, weight: .medium, design: .monospaced))
                        .tracking(1)
                        .foregroundColor(.jarvisTextDim)
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

            // Right: Provider + Voice + Date/Time + Security + Settings
            HStack(spacing: 10) {
                // Provider badge — colored dot + label
                HStack(spacing: 4) {
                    Circle()
                        .fill(providerColor)
                        .frame(width: 4, height: 4)
                        .shadow(color: providerColor.opacity(0.5), radius: 3)

                    Text(provider.uppercased())
                        .font(.system(size: 8, weight: .bold, design: .monospaced))
                        .tracking(1)
                        .foregroundColor(providerColor.opacity(0.8))
                        .lineLimit(1)
                        .fixedSize(horizontal: true, vertical: false)
                }
                .padding(.horizontal, 6)
                .padding(.vertical, 3)
                .background {
                    HexCornerShape(cutSize: 4)
                        .fill(providerColor.opacity(0.06))
                        .overlay {
                            HexCornerShape(cutSize: 4)
                                .strokeBorder(providerColor.opacity(0.15), lineWidth: 0.5)
                        }
                }
                .onTapGesture {
                    showSettings = true
                }

                // Divider
                Rectangle()
                    .fill(Color.white.opacity(0.06))
                    .frame(width: 0.5, height: 14)

                // Atlas map button
                Button {
                    showAtlas = true
                } label: {
                    Image(systemName: "map")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(.jarvisBlue.opacity(0.7))
                }

                // Voice button
                Button {
                    showVoiceMode = true
                } label: {
                    Image(systemName: "waveform")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(.jarvisBlue.opacity(0.7))
                }

                // Date + Time stacked
                VStack(alignment: .trailing, spacing: 1) {
                    Text(date)
                        .font(.system(size: 7, weight: .medium, design: .monospaced))
                        .foregroundColor(.jarvisTextDim.opacity(0.5))
                        .lineLimit(1)
                    Text(time)
                        .font(.system(size: 9, weight: .medium, design: .monospaced))
                        .foregroundColor(.jarvisTextDim)
                        .lineLimit(1)
                }
                .fixedSize()

                // Security badge and settings removed — use edge swipes instead
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .glassCapsule(opacity: 0.6)
        .padding(.horizontal, 8)
        .padding(.top, 4)
        .onReceive(timer) { _ in updateTime() }
        .onAppear { updateTime() }
    }

    private func updateTime() {
        let now = Date()
        let tf = DateFormatter()
        tf.dateFormat = "h:mm a"
        time = tf.string(from: now)
        let df = DateFormatter()
        df.dateFormat = "MMM d"
        date = df.string(from: now).uppercased()
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
