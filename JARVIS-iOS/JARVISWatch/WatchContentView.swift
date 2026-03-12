import SwiftUI
import WatchKit

struct WatchContentView: View {
    @StateObject private var voiceManager = WatchVoiceManager()
    @State private var showResponse = false

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()

            VStack(spacing: 0) {
                // JARVIS Orb — fills the screen
                JARVISEnergyOrb(
                    audioLevel: voiceManager.audioLevel,
                    isActive: voiceManager.isListening || voiceManager.isProcessing,
                    isSpeaking: voiceManager.isSpeaking
                )
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .onTapGesture {
                    handleTap()
                }

                // Status / response text at bottom
                VStack(spacing: 2) {
                    if showResponse, !voiceManager.responseText.isEmpty {
                        Text(voiceManager.responseText)
                            .font(.system(size: 11))
                            .foregroundColor(Color(hex: "00d4ff").opacity(0.8))
                            .lineLimit(3)
                            .multilineTextAlignment(.center)
                            .padding(.horizontal, 8)
                            .transition(.opacity)
                    } else {
                        Text(voiceManager.statusText)
                            .font(.system(size: 9, weight: .medium, design: .monospaced))
                            .tracking(2)
                            .foregroundColor(Color(hex: "00d4ff").opacity(0.5))
                    }
                }
                .frame(height: 36)
                .animation(.easeInOut(duration: 0.3), value: showResponse)
            }
        }
        .onChange(of: voiceManager.responseText) { _, newValue in
            if !newValue.isEmpty {
                showResponse = true
                Task {
                    try? await Task.sleep(for: .seconds(5))
                    showResponse = false
                }
            }
        }
    }

    private func handleTap() {
        if voiceManager.isListening {
            // Tap again while listening → stop and send
            voiceManager.stopAndSend()
        } else if !voiceManager.isProcessing && !voiceManager.isSpeaking {
            // Tap to start listening
            voiceManager.startListening()
        }
    }
}

// MARK: - Watch Color Extension

extension Color {
    init(hex: String) {
        let hex = hex.trimmingCharacters(in: .alphanumerics.inverted)
        var int: UInt64 = 0
        Scanner(string: hex).scanHexInt64(&int)
        let r, g, b: UInt64
        switch hex.count {
        case 6: (r, g, b) = ((int >> 16) & 0xFF, (int >> 8) & 0xFF, int & 0xFF)
        default: (r, g, b) = (0, 212, 255)
        }
        self.init(.sRGB, red: Double(r)/255, green: Double(g)/255, blue: Double(b)/255)
    }
}
