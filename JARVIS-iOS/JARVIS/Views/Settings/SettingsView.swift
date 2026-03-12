import SwiftUI

struct SettingsView: View {
    @Binding var isShowing: Bool
    @EnvironmentObject var authVM: AuthViewModel
    @EnvironmentObject var chatVM: ChatViewModel
    @State private var serverURL = JARVISConfig.baseURL

    var body: some View {
        ZStack(alignment: .trailing) {
            Color.black.opacity(0.4)
                .ignoresSafeArea()
                .onTapGesture { isShowing = false }

            VStack(spacing: 0) {
                // Header
                HStack {
                    Text("SETTINGS")
                        .font(.system(size: 10, weight: .bold, design: .monospaced))
                        .tracking(3)
                        .foregroundColor(.jarvisBlue)

                    Spacer()

                    Button { isShowing = false } label: {
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

                ScrollView {
                    VStack(spacing: 20) {
                        // User Info
                        if let user = authVM.user {
                            SettingsSection(title: "IDENTITY") {
                                SettingsRow(label: "User", value: user.username)
                                SettingsRow(label: "Email", value: user.email)
                            }
                        }

                        // Model Provider
                        SettingsSection(title: "AI PROVIDER") {
                            ForEach(chatVM.availableProviders) { provider in
                                Button {
                                    chatVM.selectedProvider = provider.id
                                } label: {
                                    HStack {
                                        Circle()
                                            .fill(
                                                provider.available
                                                    ? Color.jarvisOnline
                                                    : Color.jarvisError.opacity(0.5)
                                            )
                                            .frame(width: 5, height: 5)

                                        Text(provider.id.uppercased())
                                            .font(.system(size: 12, weight: .medium, design: .monospaced))
                                            .foregroundColor(
                                                chatVM.selectedProvider == provider.id
                                                    ? .jarvisBlue
                                                    : .jarvisText
                                            )

                                        Spacer()

                                        if chatVM.selectedProvider == provider.id {
                                            Image(systemName: "checkmark")
                                                .font(.system(size: 10, weight: .bold))
                                                .foregroundColor(.jarvisBlue)
                                        }

                                        if !provider.available {
                                            Text("OFFLINE")
                                                .font(.system(size: 8, design: .monospaced))
                                                .foregroundColor(.jarvisError.opacity(0.6))
                                        }
                                    }
                                    .padding(.vertical, 4)
                                }
                                .disabled(!provider.available)
                            }
                        }

                        // Server
                        SettingsSection(title: "CONNECTION") {
                            VStack(alignment: .leading, spacing: 6) {
                                Text("SERVER URL")
                                    .hudLabel()

                                TextField("https://app.malibupoint.dev", text: $serverURL)
                                    .font(.system(size: 12, design: .monospaced))
                                    .foregroundColor(.jarvisText)
                                    .tint(.jarvisBlue)
                                    .padding(.horizontal, 12)
                                    .padding(.vertical, 8)
                                    .background {
                                        RoundedRectangle(cornerRadius: 6)
                                            .fill(Color.jarvisBlue.opacity(0.03))
                                            .overlay {
                                                RoundedRectangle(cornerRadius: 6)
                                                    .strokeBorder(Color.jarvisBlue.opacity(0.1), lineWidth: 0.5)
                                            }
                                    }
                                    .onSubmit {
                                        UserDefaults.standard.set(serverURL, forKey: "jarvis_base_url")
                                    }
                            }
                        }

                        // About
                        SettingsSection(title: "SYSTEM") {
                            SettingsRow(label: "Version", value: "1.0.0")
                            SettingsRow(label: "Protocol", value: "JARVIS v1")
                            SettingsRow(label: "Encryption", value: "AES-256")
                        }

                        // Logout
                        Button {
                            Task {
                                await authVM.logout()
                                isShowing = false
                            }
                        } label: {
                            Text("DISCONNECT")
                                .font(.system(size: 11, weight: .medium, design: .monospaced))
                                .tracking(2)
                                .foregroundColor(.jarvisError)
                                .frame(maxWidth: .infinity)
                                .frame(height: 44)
                                .background {
                                    RoundedRectangle(cornerRadius: 8)
                                        .fill(Color.jarvisError.opacity(0.05))
                                        .overlay {
                                            RoundedRectangle(cornerRadius: 8)
                                                .strokeBorder(Color.jarvisError.opacity(0.2), lineWidth: 0.5)
                                        }
                                }
                        }
                    }
                    .padding(16)
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
                    .overlay(alignment: .leading) {
                        Rectangle()
                            .fill(Color.jarvisBlue.opacity(0.08))
                            .frame(width: 0.5)
                    }
                    .ignoresSafeArea()
            }
        }
    }
}

// MARK: - Settings Components

struct SettingsSection<Content: View>: View {
    let title: String
    @ViewBuilder let content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title)
                .font(.system(size: 9, weight: .bold, design: .monospaced))
                .tracking(2)
                .foregroundColor(.jarvisBlue.opacity(0.5))

            VStack(spacing: 6) {
                content
            }
            .padding(12)
            .glassBackground(opacity: 0.3, cornerRadius: 10)
        }
    }
}

struct SettingsRow: View {
    let label: String
    let value: String

    var body: some View {
        HStack {
            Text(label)
                .font(.system(size: 11, design: .monospaced))
                .foregroundColor(.jarvisTextDim)

            Spacer()

            Text(value)
                .font(.system(size: 11, weight: .medium, design: .monospaced))
                .foregroundColor(.jarvisText)
                .lineLimit(1)
        }
    }
}
