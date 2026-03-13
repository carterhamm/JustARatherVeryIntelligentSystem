import SwiftUI

struct LoginView: View {
    @EnvironmentObject var authVM: AuthViewModel
    @State private var showGrid = false
    @State private var ringRotation = 0.0
    @State private var bootComplete = false
    @FocusState private var focusedField: LoginField?

    private enum LoginField { case identifier, password }

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

            ScrollView {
                VStack(spacing: 0) {
                    Spacer().frame(height: 80)

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
                                    width: CGFloat(140 + i * 36),
                                    height: CGFloat(140 + i * 36)
                                )
                                .rotationEffect(.degrees(ringRotation * (i % 2 == 0 ? 1 : -0.7)))
                        }

                        // Arc segments on outer ring
                        ForEach(0..<6, id: \.self) { i in
                            ArcSegment(startAngle: Double(i) * 60 + 10, endAngle: Double(i) * 60 + 50)
                                .stroke(Color.jarvisBlue.opacity(0.4), lineWidth: 2)
                                .frame(width: 180, height: 180)
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
                                    endRadius: 60
                                )
                            )
                            .frame(width: 120, height: 120)

                        // Inner ring
                        Circle()
                            .stroke(Color.jarvisBlue.opacity(0.5), lineWidth: 1.5)
                            .frame(width: 80, height: 80)

                        // Core
                        Circle()
                            .fill(Color.jarvisBlue.opacity(0.8))
                            .frame(width: 14, height: 14)
                            .shadow(color: .jarvisBlue, radius: 15)
                            .shadow(color: .jarvisBlue, radius: 30)
                    }
                    .padding(.bottom, 36)

                    // Title
                    VStack(spacing: 12) {
                        Text("J.A.R.V.I.S.")
                            .font(.system(size: 28, weight: .thin, design: .monospaced))
                            .tracking(10)
                            .foregroundColor(.jarvisBlue)
                            .shadow(color: .jarvisBlue.opacity(0.5), radius: 10)

                        Text("JUST A RATHER VERY INTELLIGENT SYSTEM")
                            .font(.system(size: 7, weight: .medium, design: .monospaced))
                            .tracking(3)
                            .foregroundColor(.jarvisBlue.opacity(0.4))

                        Rectangle()
                            .fill(Color.jarvisBlue.opacity(0.2))
                            .frame(width: 200, height: 0.5)
                            .padding(.vertical, 6)

                        Text("MALIBU POINT SECURE ACCESS")
                            .font(.system(size: 9, weight: .medium, design: .monospaced))
                            .tracking(2)
                            .foregroundColor(.jarvisBlue.opacity(0.5))
                    }

                    Spacer().frame(height: 44)

                    // Login Form
                    if bootComplete {
                        VStack(spacing: 14) {
                            // Identifier field
                            VStack(alignment: .leading, spacing: 6) {
                                Text("IDENTIFICATION")
                                    .font(.system(size: 8, weight: .semibold, design: .monospaced))
                                    .tracking(2)
                                    .foregroundColor(.jarvisBlue.opacity(0.5))

                                TextField("", text: $authVM.identifier, prompt: Text("Username or email").foregroundColor(Color.white.opacity(0.2)))
                                    .font(.system(size: 14, design: .monospaced))
                                    .foregroundColor(.white)
                                    .textContentType(.username)
                                    .textInputAutocapitalization(.never)
                                    .autocorrectionDisabled()
                                    .focused($focusedField, equals: .identifier)
                                    .padding(.horizontal, 16)
                                    .padding(.vertical, 14)
                                    .background(
                                        RoundedRectangle(cornerRadius: 8)
                                            .fill(Color.white.opacity(0.03))
                                            .overlay(
                                                RoundedRectangle(cornerRadius: 8)
                                                    .strokeBorder(
                                                        focusedField == .identifier
                                                            ? Color.jarvisBlue.opacity(0.5)
                                                            : Color.jarvisBlue.opacity(0.15),
                                                        lineWidth: 1
                                                    )
                                            )
                                    )
                                    .onSubmit { focusedField = .password }
                            }

                            // Password field
                            VStack(alignment: .leading, spacing: 6) {
                                Text("PASSPHRASE")
                                    .font(.system(size: 8, weight: .semibold, design: .monospaced))
                                    .tracking(2)
                                    .foregroundColor(.jarvisBlue.opacity(0.5))

                                SecureField("", text: $authVM.password, prompt: Text("Enter passphrase").foregroundColor(Color.white.opacity(0.2)))
                                    .font(.system(size: 14, design: .monospaced))
                                    .foregroundColor(.white)
                                    .textContentType(.password)
                                    .focused($focusedField, equals: .password)
                                    .padding(.horizontal, 16)
                                    .padding(.vertical, 14)
                                    .background(
                                        RoundedRectangle(cornerRadius: 8)
                                            .fill(Color.white.opacity(0.03))
                                            .overlay(
                                                RoundedRectangle(cornerRadius: 8)
                                                    .strokeBorder(
                                                        focusedField == .password
                                                            ? Color.jarvisBlue.opacity(0.5)
                                                            : Color.jarvisBlue.opacity(0.15),
                                                        lineWidth: 1
                                                    )
                                            )
                                    )
                                    .onSubmit {
                                        focusedField = nil
                                        Task { await authVM.loginWithPassword() }
                                    }
                            }

                            Spacer().frame(height: 6)

                            // Sign In Button
                            Button {
                                focusedField = nil
                                Task { await authVM.loginWithPassword() }
                            } label: {
                                HStack(spacing: 12) {
                                    if authVM.isLoading {
                                        ProgressView()
                                            .tint(.jarvisBlue)
                                            .scaleEffect(0.8)
                                    } else {
                                        Image(systemName: "shield.checkered")
                                            .font(.system(size: 16))
                                        Text("SIGN IN WITH J.A.R.V.I.S.")
                                            .font(.system(size: 12, weight: .semibold, design: .monospaced))
                                            .tracking(2)
                                    }
                                }
                                .foregroundColor(.jarvisBlue)
                                .frame(maxWidth: .infinity)
                                .frame(height: 52)
                                .background(
                                    RoundedRectangle(cornerRadius: 8)
                                        .fill(Color.jarvisBlue.opacity(0.1))
                                        .overlay(
                                            RoundedRectangle(cornerRadius: 8)
                                                .strokeBorder(Color.jarvisBlue.opacity(0.4), lineWidth: 1)
                                        )
                                )
                            }
                            .disabled(authVM.isLoading)
                            .cyanGlow(radius: 12, opacity: 0.2)

                            // Passkey alternative
                            Button {
                                // Passkey auth — future enhancement
                            } label: {
                                HStack(spacing: 8) {
                                    Image(systemName: "person.badge.key.fill")
                                        .font(.system(size: 12))
                                    Text("USE PASSKEY")
                                        .font(.system(size: 10, weight: .medium, design: .monospaced))
                                        .tracking(2)
                                }
                                .foregroundColor(.jarvisBlue.opacity(0.4))
                                .frame(maxWidth: .infinity)
                                .frame(height: 40)
                                .background(
                                    RoundedRectangle(cornerRadius: 8)
                                        .fill(Color.clear)
                                        .overlay(
                                            RoundedRectangle(cornerRadius: 8)
                                                .strokeBorder(Color.jarvisBlue.opacity(0.1), lineWidth: 0.5)
                                        )
                                )
                            }

                            if let error = authVM.error {
                                Text(error)
                                    .font(.system(size: 11, design: .monospaced))
                                    .foregroundColor(.jarvisError)
                                    .multilineTextAlignment(.center)
                                    .padding(.top, 4)
                            }
                        }
                        .padding(.horizontal, 40)
                        .transition(.opacity.combined(with: .move(edge: .bottom)))
                    }

                    Spacer().frame(height: 40)

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
            .scrollDismissesKeyboard(.interactively)
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
