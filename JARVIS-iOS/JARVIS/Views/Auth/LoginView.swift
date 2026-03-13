import SwiftUI
import AuthenticationServices

struct LoginView: View {
    @EnvironmentObject var authVM: AuthViewModel
    @State private var showGrid = false
    @State private var bootComplete = false
    @FocusState private var identifierFocused: Bool
    @FocusState private var totpFocused: Bool

    var body: some View {
        ZStack {
            Color.jarvisDeepDark.ignoresSafeArea()

            if showGrid {
                GridBackground()
                    .opacity(0.3)
            }

            ScanlineOverlay()

            ScrollView {
                VStack(spacing: 0) {
                    Spacer().frame(height: 40)

                    // JARVIS Core Visual — Arc Reactor
                    ZStack {
                        // Outer ring
                        Circle()
                            .stroke(Color.jarvisBlue.opacity(0.35), lineWidth: 1.5)
                            .frame(width: 100, height: 100)

                        // Inner glow
                        Circle()
                            .fill(
                                RadialGradient(
                                    colors: [
                                        Color.jarvisBlue.opacity(0.6),
                                        Color.jarvisBlue.opacity(0.1),
                                        .clear
                                    ],
                                    center: .center,
                                    startRadius: 5,
                                    endRadius: 40
                                )
                            )
                            .frame(width: 80, height: 80)

                        // Core dot
                        Circle()
                            .fill(Color.jarvisBlue.opacity(0.9))
                            .frame(width: 12, height: 12)
                            .shadow(color: .jarvisBlue, radius: 12)
                            .shadow(color: .jarvisBlue, radius: 24)
                    }
                    .padding(.bottom, 24)

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

                        Text("STARK SECURE SERVER")
                            .font(.system(size: 9, weight: .medium, design: .monospaced))
                            .tracking(2)
                            .foregroundColor(.jarvisBlue.opacity(0.5))
                    }

                    Spacer().frame(height: 44)

                    // Login Steps
                    if bootComplete {
                        VStack(spacing: 14) {
                            switch authVM.authStep {
                            case .identify:
                                identifyStep
                            case .totp:
                                totpStep
                            case .authenticate:
                                authenticateStep
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
            withAnimation(.easeOut(duration: 1).delay(1)) {
                showGrid = true
            }
            withAnimation(.easeOut(duration: 0.8).delay(1.5)) {
                bootComplete = true
            }
        }
    }

    // MARK: - Step 1: Identify

    private var identifyStep: some View {
        VStack(spacing: 14) {
            VStack(alignment: .leading, spacing: 6) {
                Text("IDENTIFICATION")
                    .font(.system(size: 8, weight: .semibold, design: .monospaced))
                    .tracking(2)
                    .foregroundColor(.jarvisBlue.opacity(0.5))

                TextField(
                    "",
                    text: $authVM.identifier,
                    prompt: Text("Username or email")
                        .foregroundColor(Color.white.opacity(0.2))
                )
                .font(.system(size: 14, design: .monospaced))
                .foregroundColor(.white)
                .textContentType(.username)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .focused($identifierFocused)
                .padding(.horizontal, 16)
                .padding(.vertical, 14)
                .background(inputBackground(focused: identifierFocused))
                .onSubmit {
                    identifierFocused = false
                    Task { await authVM.lookupUser() }
                }
            }

            Spacer().frame(height: 6)

            Button {
                identifierFocused = false
                Task { await authVM.lookupUser() }
            } label: {
                HStack(spacing: 12) {
                    if authVM.isLoading {
                        ProgressView()
                            .tint(.jarvisBlue)
                            .scaleEffect(0.8)
                    } else {
                        Image(systemName: "arrow.right.circle")
                            .font(.system(size: 16))
                        Text("CONTINUE")
                            .font(.system(size: 12, weight: .semibold, design: .monospaced))
                            .tracking(2)
                    }
                }
                .foregroundColor(.jarvisBlue)
                .frame(maxWidth: .infinity)
                .frame(height: 52)
                .background(buttonBackground)
            }
            .disabled(authVM.isLoading || authVM.identifier.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            .cyanGlow(radius: 12, opacity: 0.2)
        }
    }

    // MARK: - Step 2: TOTP

    private var totpStep: some View {
        VStack(spacing: 14) {
            // Back button
            backButton

            VStack(spacing: 6) {
                Text("TWO-FACTOR AUTHENTICATION")
                    .font(.system(size: 8, weight: .semibold, design: .monospaced))
                    .tracking(2)
                    .foregroundColor(.jarvisBlue.opacity(0.5))

                Text("Enter the 6-digit code from your authenticator")
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundColor(.jarvisTextDim)
                    .multilineTextAlignment(.center)
            }

            TextField(
                "",
                text: $authVM.totpCode,
                prompt: Text("000000")
                    .foregroundColor(Color.white.opacity(0.15))
            )
            .font(.system(size: 28, weight: .medium, design: .monospaced))
            .foregroundColor(.jarvisBlue)
            .multilineTextAlignment(.center)
            .keyboardType(.numberPad)
            .textContentType(.oneTimeCode)
            .focused($totpFocused)
            .padding(.horizontal, 16)
            .padding(.vertical, 14)
            .background(inputBackground(focused: totpFocused))
            .onChange(of: authVM.totpCode) { _, newValue in
                // Limit to 6 digits
                let filtered = String(newValue.prefix(6).filter(\.isNumber))
                if filtered != newValue {
                    authVM.totpCode = filtered
                }
                // Auto-advance when 6 digits entered
                if filtered.count == 6 {
                    totpFocused = false
                    authVM.submitTOTP()
                }
            }
            .onAppear { totpFocused = true }

            Spacer().frame(height: 6)

            Button {
                totpFocused = false
                authVM.submitTOTP()
            } label: {
                HStack(spacing: 12) {
                    Image(systemName: "checkmark.shield")
                        .font(.system(size: 16))
                    Text("VERIFY CODE")
                        .font(.system(size: 12, weight: .semibold, design: .monospaced))
                        .tracking(2)
                }
                .foregroundColor(.jarvisBlue)
                .frame(maxWidth: .infinity)
                .frame(height: 52)
                .background(buttonBackground)
            }
            .disabled(authVM.totpCode.count != 6)
            .cyanGlow(radius: 12, opacity: 0.2)
        }
    }

    // MARK: - Step 3: Passkey Authenticate

    private var authenticateStep: some View {
        VStack(spacing: 14) {
            // Back button
            backButton

            VStack(spacing: 8) {
                if let name = authVM.lookupResult?.fullName {
                    Text("Welcome, \(name)")
                        .font(.system(size: 16, weight: .light, design: .monospaced))
                        .foregroundColor(.jarvisText)
                } else {
                    Text("Welcome")
                        .font(.system(size: 16, weight: .light, design: .monospaced))
                        .foregroundColor(.jarvisText)
                }

                Text("Verify your identity to continue")
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundColor(.jarvisTextDim)
            }
            .padding(.bottom, 8)

            Button {
                guard let window = UIApplication.shared.connectedScenes
                    .compactMap({ $0 as? UIWindowScene })
                    .flatMap(\.windows)
                    .first(where: \.isKeyWindow) else { return }
                Task { await authVM.beginPasskeyAuth(anchor: window) }
            } label: {
                HStack(spacing: 12) {
                    if authVM.isLoading {
                        ProgressView()
                            .tint(.jarvisBlue)
                            .scaleEffect(0.8)
                    } else {
                        Image(systemName: "person.badge.key.fill")
                            .font(.system(size: 18))
                        Text("VERIFY IDENTITY")
                            .font(.system(size: 12, weight: .semibold, design: .monospaced))
                            .tracking(2)
                    }
                }
                .foregroundColor(.jarvisBlue)
                .frame(maxWidth: .infinity)
                .frame(height: 52)
                .background(buttonBackground)
            }
            .disabled(authVM.isLoading)
            .cyanGlow(radius: 12, opacity: 0.2)
        }
    }

    // MARK: - Shared Components

    private var backButton: some View {
        HStack {
            Button {
                authVM.goBack()
            } label: {
                HStack(spacing: 4) {
                    Image(systemName: "chevron.left")
                        .font(.system(size: 10, weight: .bold))
                    Text("BACK")
                        .font(.system(size: 9, weight: .medium, design: .monospaced))
                        .tracking(1)
                }
                .foregroundColor(.jarvisBlue.opacity(0.5))
            }
            Spacer()
        }
    }

    private func inputBackground(focused: Bool) -> some View {
        HexCornerShape(cutSize: 8)
            .fill(Color.white.opacity(0.03))
            .overlay(
                HexCornerShape(cutSize: 8)
                    .strokeBorder(
                        focused
                            ? Color.jarvisBlue.opacity(0.5)
                            : Color.jarvisBlue.opacity(0.15),
                        lineWidth: 1
                    )
            )
    }

    private var buttonBackground: some View {
        ZStack {
            HexCornerShape(cutSize: 8)
                .fill(Color.jarvisBlue.opacity(0.1))
                .overlay(
                    HexCornerShape(cutSize: 8)
                        .strokeBorder(Color.jarvisBlue.opacity(0.4), lineWidth: 1)
                )
            HUDCornerAccents(cutSize: 8, color: .jarvisBlue, opacity: 0.4, lineLength: 10)
        }
    }
}

// MARK: - Grid Background

struct GridBackground: View {
    var body: some View {
        Canvas { context, size in
            let spacing: CGFloat = 40

            var x: CGFloat = 0
            while x < size.width {
                var path = Path()
                path.move(to: CGPoint(x: x, y: 0))
                path.addLine(to: CGPoint(x: x, y: size.height))
                context.stroke(path, with: .color(Color.jarvisBlue.opacity(0.04)), lineWidth: 0.5)
                x += spacing
            }

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
