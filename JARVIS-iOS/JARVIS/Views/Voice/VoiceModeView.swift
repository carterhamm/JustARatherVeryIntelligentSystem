import SwiftUI

struct VoiceModeView: View {
    @Binding var isShowing: Bool
    @EnvironmentObject var chatVM: ChatViewModel
    @StateObject private var voiceService = VoiceService.shared
    @State private var phase: VoicePhase = .idle
    @State private var responseText = ""
    @State private var errorText: String?

    enum VoicePhase {
        case idle, listening, processing, responding
    }

    var body: some View {
        ZStack {
            // Full black background
            Color.black.ignoresSafeArea()

            VStack(spacing: 0) {
                // Close button
                HStack {
                    Spacer()
                    Button {
                        if voiceService.isRecording {
                            _ = voiceService.stopListening()
                        }
                        isShowing = false
                    } label: {
                        Image(systemName: "xmark")
                            .font(.system(size: 16, weight: .medium))
                            .foregroundColor(.jarvisBlue.opacity(0.5))
                            .frame(width: 36, height: 36)
                            .background {
                                HexCornerShape(cutSize: 6)
                                    .fill(Color.jarvisBlue.opacity(0.05))
                                    .overlay {
                                        HexCornerShape(cutSize: 6)
                                            .strokeBorder(Color.jarvisBlue.opacity(0.15), lineWidth: 0.5)
                                    }
                            }
                    }
                    .padding(.trailing, 20)
                    .padding(.top, 16)
                }

                Spacer()

                // JARVIS Orb
                JARVISVoiceOrb(
                    audioLevel: voiceService.audioLevel,
                    phase: orbPhaseBinding
                )
                .frame(width: 240, height: 240)

                Spacer().frame(height: 40)

                // Status text
                VStack(spacing: 8) {
                    Text(statusText)
                        .font(.system(size: 10, weight: .medium, design: .monospaced))
                        .tracking(3)
                        .foregroundColor(.jarvisBlue.opacity(0.6))

                    if !voiceService.transcribedText.isEmpty && phase == .listening {
                        Text(voiceService.transcribedText)
                            .font(.system(size: 14, weight: .light))
                            .foregroundColor(.jarvisText)
                            .multilineTextAlignment(.center)
                            .padding(.horizontal, 40)
                            .transition(.opacity)
                    }

                    if !responseText.isEmpty && phase == .responding {
                        Text(responseText)
                            .font(.system(size: 14, weight: .light))
                            .foregroundColor(.jarvisBlue.opacity(0.8))
                            .multilineTextAlignment(.center)
                            .padding(.horizontal, 30)
                            .transition(.opacity)
                    }

                    if let err = errorText {
                        Text(err)
                            .font(.system(size: 11, design: .monospaced))
                            .foregroundColor(.jarvisError)
                    }
                }
                .animation(.easeInOut, value: phase)

                Spacer()

                // Mic button
                Button {
                    handleMicTap()
                } label: {
                    ZStack {
                        HexCornerShape(cutSize: 12)
                            .fill(phase == .listening ? Color.jarvisBlue.opacity(0.15) : Color.clear)
                            .frame(width: 72, height: 72)
                            .overlay {
                                HexCornerShape(cutSize: 12)
                                    .strokeBorder(
                                        phase == .listening
                                            ? Color.jarvisBlue.opacity(0.5)
                                            : Color.jarvisBlue.opacity(0.2),
                                        lineWidth: 1.5
                                    )
                            }

                        Image(systemName: phase == .listening ? "stop.fill" : "mic.fill")
                            .font(.system(size: 24))
                            .foregroundColor(.jarvisBlue)
                    }
                    .cyanGlow(radius: phase == .listening ? 20 : 0, opacity: 0.3)
                }
                .disabled(phase == .processing)
                .padding(.bottom, 50)
            }
        }
        .task {
            let granted = await voiceService.requestPermissions()
            if !granted {
                errorText = "Microphone or speech recognition permission denied"
            }
        }
    }

    private var orbPhaseBinding: JARVISVoiceOrb.OrbPhase {
        switch phase {
        case .idle: return .idle
        case .listening: return .listening
        case .processing: return .thinking
        case .responding: return .speaking
        }
    }

    private var statusText: String {
        switch phase {
        case .idle: return "TAP TO SPEAK"
        case .listening: return "LISTENING"
        case .processing: return "PROCESSING"
        case .responding: return "JARVIS"
        }
    }

    private func handleMicTap() {
        switch phase {
        case .idle:
            phase = .listening
            voiceService.startListening()

        case .listening:
            let text = voiceService.stopListening()
            guard !text.isEmpty else {
                phase = .idle
                return
            }
            phase = .processing
            Task {
                await sendVoiceMessage(text)
            }

        default:
            break
        }
    }

    private func sendVoiceMessage(_ text: String) async {
        do {
            // Use the chat stream
            chatVM.inputText = text
            await chatVM.sendMessage()

            if let lastAssistant = chatVM.messages.last(where: { $0.role == .assistant }) {
                responseText = lastAssistant.content
                phase = .responding

                // Speak the response
                await voiceService.speak(lastAssistant.content)

                try? await Task.sleep(for: .seconds(2))
                responseText = ""
                phase = .idle
            } else {
                phase = .idle
            }
        }
    }
}

// MARK: - JARVIS Voice Orb (iOS Version)

struct JARVISVoiceOrb: View {
    let audioLevel: Float
    let phase: OrbPhase

    enum OrbPhase {
        case idle, listening, thinking, speaking
    }

    @State private var time: Double = 0
    @State private var innerRotation = 0.0

    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0/60.0)) { timeline in
            Canvas { context, size in
                let center = CGPoint(x: size.width / 2, y: size.height / 2)
                let baseRadius = min(size.width, size.height) * 0.38
                let t = timeline.date.timeIntervalSinceReferenceDate

                // Outer glow
                let glowRadius = baseRadius * 1.4
                let glowRect = CGRect(
                    x: center.x - glowRadius,
                    y: center.y - glowRadius,
                    width: glowRadius * 2,
                    height: glowRadius * 2
                )
                context.opacity = 0.15 + Double(audioLevel) * 0.15
                context.fill(
                    Path(ellipseIn: glowRect),
                    with: .radialGradient(
                        Gradient(colors: [
                            Color.jarvisBlue.opacity(0.3),
                            Color.jarvisBlue.opacity(0.05),
                            .clear
                        ]),
                        center: center,
                        startRadius: baseRadius * 0.5,
                        endRadius: glowRadius
                    )
                )
                context.opacity = 1

                // Multiple ring layers for depth
                for layer in 0..<4 {
                    let layerFactor = Double(layer) / 4.0
                    let ringRadius = baseRadius * (0.85 + layerFactor * 0.15)
                    let thickness = 3.0 + Double(audioLevel) * 8.0 * (1 - layerFactor * 0.5)
                    let opacity = 0.6 - layerFactor * 0.12

                    drawEnergyRing(
                        in: &context,
                        center: center,
                        radius: ringRadius,
                        thickness: CGFloat(thickness),
                        time: t + layerFactor * 2,
                        speed: 0.3 + layerFactor * 0.2,
                        opacity: opacity,
                        audioLevel: Double(audioLevel),
                        segments: 120
                    )
                }

                // Inner core glow
                let coreRadius = baseRadius * 0.2 * (1 + Double(audioLevel) * 0.3)
                let coreRect = CGRect(
                    x: center.x - coreRadius,
                    y: center.y - coreRadius,
                    width: coreRadius * 2,
                    height: coreRadius * 2
                )
                context.fill(
                    Path(ellipseIn: coreRect),
                    with: .radialGradient(
                        Gradient(colors: [
                            Color.jarvisBlue.opacity(0.4 + Double(audioLevel) * 0.3),
                            Color.jarvisBlue.opacity(0.1),
                            .clear
                        ]),
                        center: center,
                        startRadius: 0,
                        endRadius: coreRadius
                    )
                )
            }
        }
    }

    private func drawEnergyRing(
        in context: inout GraphicsContext,
        center: CGPoint,
        radius: Double,
        thickness: CGFloat,
        time: Double,
        speed: Double,
        opacity: Double,
        audioLevel: Double,
        segments: Int
    ) {
        var path = Path()
        let step = (2 * Double.pi) / Double(segments)

        for i in 0...segments {
            let angle = Double(i) * step

            // Noise-based radius perturbation for organic feel
            let noise1 = sin(angle * 3 + time * speed) * 0.02
            let noise2 = sin(angle * 7 - time * speed * 1.3) * 0.015
            let noise3 = cos(angle * 5 + time * speed * 0.7) * 0.01
            let audioNoise = sin(angle * 2 + time * 1.5) * audioLevel * 0.04
            let r = radius * (1 + noise1 + noise2 + noise3 + audioNoise)

            let x = center.x + cos(angle) * r
            let y = center.y + sin(angle) * r

            if i == 0 {
                path.move(to: CGPoint(x: x, y: y))
            } else {
                path.addLine(to: CGPoint(x: x, y: y))
            }
        }
        path.closeSubpath()

        context.stroke(
            path,
            with: .color(Color.jarvisBlue.opacity(opacity)),
            style: StrokeStyle(
                lineWidth: thickness,
                lineCap: .round,
                lineJoin: .round
            )
        )
    }
}
