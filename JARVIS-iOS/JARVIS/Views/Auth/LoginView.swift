import SwiftUI
import AuthenticationServices

struct LoginView: View {
    @EnvironmentObject var authVM: AuthViewModel
    @State private var showGrid = false
    @State private var ringRotation = 0.0
    @State private var bootComplete = false

    var body: some View {
        ZStack {
            // Background
            Color.jarvisDeepDark.ignoresSafeArea()

            // Subtle grid
            if showGrid {
                GridBackground()
                    .opacity(0.3)
            }

            // Scanline
            ScanlineOverlay()

            VStack(spacing: 0) {
                Spacer()

                // JARVIS Core Visual
                ZStack {
                    // Outer rotating rings
                    ForEach(0..<3, id: \.self) { i in
                        Circle()
                            .stroke(
                                Color.jarvisBlue.opacity(0.1 + Double(i) * 0.1),
                                lineWidth: 1
                            )
                            .frame(
                                width: CGFloat(160 + i * 40),
                                height: CGFloat(160 + i * 40)
                            )
                            .rotationEffect(.degrees(ringRotation * (i % 2 == 0 ? 1 : -0.7)))
                    }

                    // Arc segments on outer ring
                    ForEach(0..<6, id: \.self) { i in
                        ArcSegment(startAngle: Double(i) * 60 + 10, endAngle: Double(i) * 60 + 50)
                            .stroke(Color.jarvisBlue.opacity(0.4), lineWidth: 2)
                            .frame(width: 200, height: 200)
                            .rotationEffect(.degrees(ringRotation * 0.3))
                    }

                    // Core glow
                    Circle()
                        .fill(
                            RadialGradient(
                                colors: [
                                    Color.jarvisBlue.opacity(0.6),
                                    Color.jarvisBlue.opacity(0.1),
                                    .clear
                                ],
                                center: .center,
                                startRadius: 10,
                                endRadius: 70
                            )
                        )
                        .frame(width: 140, height: 140)

                    // Inner ring
                    Circle()
                        .stroke(Color.jarvisBlue.opacity(0.5), lineWidth: 1.5)
                        .frame(width: 90, height: 90)

                    // Core
                    Circle()
                        .fill(Color.jarvisBlue.opacity(0.8))
                        .frame(width: 16, height: 16)
                        .shadow(color: .jarvisBlue, radius: 15)
                        .shadow(color: .jarvisBlue, radius: 30)
                }
                .padding(.bottom, 50)

                // Title
                VStack(spacing: 12) {
                    Text("J.A.R.V.I.S.")
                        .font(.system(size: 32, weight: .thin, design: .monospaced))
                        .tracking(10)
                        .foregroundColor(.jarvisBlue)
                        .shadow(color: .jarvisBlue.opacity(0.5), radius: 10)

                    Text("JUST A RATHER VERY INTELLIGENT SYSTEM")
                        .font(.system(size: 8, weight: .medium, design: .monospaced))
                        .tracking(3)
                        .foregroundColor(.jarvisBlue.opacity(0.4))

                    Rectangle()
                        .fill(Color.jarvisBlue.opacity(0.2))
                        .frame(width: 200, height: 0.5)
                        .padding(.vertical, 8)

                    Text("MALIBU POINT SECURE ACCESS")
                        .font(.system(size: 9, weight: .medium, design: .monospaced))
                        .tracking(2)
                        .foregroundColor(.jarvisBlue.opacity(0.5))
                }

                Spacer().frame(height: 60)

                // Passkey Login Button
                if bootComplete {
                    VStack(spacing: 16) {
                        // Passkey auth button
                        Button {
                            // Trigger passkey with ASAuthorizationController
                        } label: {
                            HStack(spacing: 12) {
                                Image(systemName: "person.badge.key.fill")
                                    .font(.system(size: 16))
                                Text("AUTHENTICATE")
                                    .font(.system(size: 13, weight: .medium, design: .monospaced))
                                    .tracking(3)
                            }
                            .foregroundColor(.jarvisBlue)
                            .frame(maxWidth: .infinity)
                            .frame(height: 52)
                            .background {
                                RoundedRectangle(cornerRadius: 8)
                                    .fill(Color.jarvisBlue.opacity(0.08))
                                    .overlay {
                                        RoundedRectangle(cornerRadius: 8)
                                            .strokeBorder(Color.jarvisBlue.opacity(0.3), lineWidth: 1)
                                    }
                            }
                        }
                        .cyanGlow(radius: 12, opacity: 0.15)

                        // SignInWithApple as alternative
                        SignInWithAppleButton(.signIn) { request in
                            request.requestedScopes = [.email, .fullName]
                        } onCompletion: { result in
                            // Handle Apple Sign In
                        }
                        .signInWithAppleButtonStyle(.white)
                        .frame(height: 50)
                        .cornerRadius(8)
                        .opacity(0.7)

                        if let error = authVM.error {
                            Text(error)
                                .font(.system(size: 11, design: .monospaced))
                                .foregroundColor(.jarvisError)
                                .multilineTextAlignment(.center)
                                .padding(.top, 8)
                        }
                    }
                    .padding(.horizontal, 40)
                    .transition(.opacity.combined(with: .move(edge: .bottom)))
                }

                Spacer()

                // Bottom HUD
                HStack {
                    Text("STARK INDUSTRIES")
                        .hudLabel()
                    Spacer()
                    Text("v1.0.0")
                        .hudLabel()
                }
                .padding(.horizontal, 24)
                .padding(.bottom, 8)
            }
        }
        .onAppear {
            withAnimation(.linear(duration: 40).repeatForever(autoreverses: false)) {
                ringRotation = 360
            }
            withAnimation(.easeOut(duration: 1).delay(1)) {
                showGrid = true
            }
            withAnimation(.easeOut(duration: 0.8).delay(1.5)) {
                bootComplete = true
            }
        }
    }
}

// MARK: - Arc Segment Shape

struct ArcSegment: Shape {
    let startAngle: Double
    let endAngle: Double

    func path(in rect: CGRect) -> Path {
        Path { p in
            p.addArc(
                center: CGPoint(x: rect.midX, y: rect.midY),
                radius: min(rect.width, rect.height) / 2,
                startAngle: .degrees(startAngle),
                endAngle: .degrees(endAngle),
                clockwise: false
            )
        }
    }
}

// MARK: - Grid Background

struct GridBackground: View {
    var body: some View {
        Canvas { context, size in
            let spacing: CGFloat = 40

            // Vertical lines
            var x: CGFloat = 0
            while x < size.width {
                var path = Path()
                path.move(to: CGPoint(x: x, y: 0))
                path.addLine(to: CGPoint(x: x, y: size.height))
                context.stroke(path, with: .color(Color.jarvisBlue.opacity(0.04)), lineWidth: 0.5)
                x += spacing
            }

            // Horizontal lines
            var y: CGFloat = 0
            while y < size.height {
                var path = Path()
                path.move(to: CGPoint(x: 0, y: y))
                path.addLine(to: CGPoint(x: size.width, y: y))
                context.stroke(path, with: .color(Color.jarvisBlue.opacity(0.04)), lineWidth: 0.5)
                y += spacing
            }
        }
        .ignoresSafeArea()
    }
}
