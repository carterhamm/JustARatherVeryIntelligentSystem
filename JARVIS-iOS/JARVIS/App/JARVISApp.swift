import SwiftUI

@main
struct JARVISApp: App {
    @StateObject private var authVM = AuthViewModel()
    @StateObject private var chatVM = ChatViewModel()
    @StateObject private var locationService = LocationService.shared
    @Environment(\.scenePhase) private var scenePhase

    init() {
        // Register background task before scene setup
        HealthSyncService.registerBackgroundTask()
    }

    var body: some Scene {
        WindowGroup {
            ZStack {
                Color.jarvisDeepDark.ignoresSafeArea()

                if authVM.isLoading {
                    BootView()
                } else if authVM.isAuthenticated {
                    MainView()
                        .environmentObject(authVM)
                        .environmentObject(chatVM)
                        .environmentObject(locationService)
                        .transition(.opacity)
                } else if authVM.needsTOTP {
                    TOTPVerifyView()
                        .environmentObject(authVM)
                        .transition(.opacity)
                } else {
                    LoginView()
                        .environmentObject(authVM)
                        .transition(.opacity)
                }
            }
            .animation(.easeInOut(duration: 0.5), value: authVM.isAuthenticated)
            .animation(.easeInOut(duration: 0.5), value: authVM.isLoading)
            .preferredColorScheme(.dark)
            .task {
                await authVM.restoreSession()
            }
            .onOpenURL { url in
                handleUniversalLink(url)
            }
            .onChange(of: authVM.isAuthenticated) { _, isAuth in
                if isAuth {
                    locationService.startTracking()
                    Task {
                        let healthService = HealthSyncService.shared
                        let authorized = await healthService.requestAuthorization()
                        if authorized {
                            await healthService.startBackgroundSync()
                        }
                    }
                } else {
                    locationService.stopTracking()
                }
            }
            .onChange(of: scenePhase) { _, phase in
                guard authVM.isAuthenticated else { return }
                switch phase {
                case .active:
                    locationService.enterForeground()
                    // Foreground catch-up: flush outbox + sync
                    Task {
                        await HealthSyncService.shared.flushOutbox()
                    }
                case .background:
                    locationService.enterBackground()
                    HealthSyncService.scheduleBackgroundRefresh()
                case .inactive:
                    break
                @unknown default:
                    break
                }
            }
        }
    }

    private func handleUniversalLink(_ url: URL) {
        guard let components = URLComponents(url: url, resolvingAgainstBaseURL: false) else { return }
        let path = components.path

        // Route based on URL path
        if path.hasPrefix("/chat/") || path.hasPrefix("/api/v1/chat/conversations/") {
            // Extract conversation ID and select it
            let segments = path.split(separator: "/")
            if let convId = segments.last {
                Task {
                    let conv = ConversationResponse(
                        id: String(convId),
                        title: nil,
                        model: nil,
                        systemPrompt: nil,
                        isArchived: false,
                        messageCount: 0,
                        lastMessageAt: nil,
                        createdAt: "",
                        updatedAt: ""
                    )
                    await chatVM.selectConversation(conv)
                }
            }
        }
        // Additional routes can be added here
    }
}

// MARK: - Boot Splash

struct BootView: View {
    @State private var opacity = 0.0
    @State private var scale = 0.8
    @State private var textOpacity = 0.0

    var body: some View {
        VStack(spacing: 30) {
            // Arc Reactor
            ZStack {
                // Outer ring
                Circle()
                    .stroke(Color.jarvisBlue.opacity(0.3), lineWidth: 2)
                    .frame(width: 100, height: 100)

                Circle()
                    .stroke(Color.jarvisBlue.opacity(0.6), lineWidth: 1)
                    .frame(width: 80, height: 80)

                // Core glow
                Circle()
                    .fill(
                        RadialGradient(
                            colors: [
                                Color.jarvisBlue.opacity(0.8),
                                Color.jarvisBlue.opacity(0.2),
                                .clear
                            ],
                            center: .center,
                            startRadius: 5,
                            endRadius: 40
                        )
                    )
                    .frame(width: 80, height: 80)

                // Core
                Circle()
                    .fill(Color.jarvisBlue)
                    .frame(width: 12, height: 12)
                    .shadow(color: .jarvisBlue, radius: 20)

                // Rotating segments
                ForEach(0..<3, id: \.self) { i in
                    RoundedRectangle(cornerRadius: 2)
                        .fill(Color.jarvisBlue.opacity(0.4))
                        .frame(width: 4, height: 25)
                        .offset(y: -35)
                        .rotationEffect(.degrees(Double(i) * 120))
                }
                .rotationEffect(.degrees(opacity * 360))
            }
            .scaleEffect(scale)

            VStack(spacing: 8) {
                Text("J.A.R.V.I.S.")
                    .font(.system(size: 28, weight: .light, design: .monospaced))
                    .tracking(8)
                    .foregroundColor(.jarvisBlue)

                Text("INITIALIZING SYSTEMS")
                    .font(.system(size: 10, weight: .medium, design: .monospaced))
                    .tracking(4)
                    .foregroundColor(.jarvisBlue.opacity(0.5))
            }
            .opacity(textOpacity)
        }
        .onAppear {
            withAnimation(.easeOut(duration: 1.5)) {
                opacity = 1
                scale = 1
            }
            withAnimation(.easeOut(duration: 1.5).delay(0.5)) {
                textOpacity = 1
            }
        }
    }
}
