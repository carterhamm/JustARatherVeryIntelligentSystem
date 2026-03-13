import SwiftUI

struct TOTPVerifyView: View {
    @EnvironmentObject var authVM: AuthViewModel
    @FocusState private var isFocused: Bool

    var body: some View {
        ZStack {
            Color.jarvisDeepDark.ignoresSafeArea()
            ScanlineOverlay()

            VStack(spacing: 40) {
                Spacer()

                // Lock icon
                ZStack {
                    HexCornerShape(cutSize: 12)
                        .stroke(Color.jarvisBlue.opacity(0.3), lineWidth: 1)
                        .frame(width: 80, height: 80)

                    Image(systemName: "lock.shield.fill")
                        .font(.system(size: 32))
                        .foregroundColor(.jarvisBlue)
                        .shadow(color: .jarvisBlue.opacity(0.5), radius: 10)
                }

                VStack(spacing: 8) {
                    Text("TWO-FACTOR AUTHENTICATION")
                        .font(.system(size: 12, weight: .medium, design: .monospaced))
                        .tracking(3)
                        .foregroundColor(.jarvisBlue)

                    Text("Enter the 6-digit code from your authenticator")
                        .font(.system(size: 11, design: .monospaced))
                        .foregroundColor(.jarvisTextDim)
                        .multilineTextAlignment(.center)
                }

                // TOTP Code Input
                VStack(spacing: 16) {
                    HStack(spacing: 12) {
                        ForEach(0..<6, id: \.self) { index in
                            let char = index < authVM.totpCode.count
                                ? String(authVM.totpCode[authVM.totpCode.index(
                                    authVM.totpCode.startIndex, offsetBy: index
                                )])
                                : ""

                            Text(char)
                                .font(.system(size: 24, weight: .medium, design: .monospaced))
                                .foregroundColor(.jarvisBlue)
                                .frame(width: 40, height: 52)
                                .background {
                                    HexCornerShape(cutSize: 6)
                                        .fill(Color.jarvisBlue.opacity(0.05))
                                        .overlay {
                                            HexCornerShape(cutSize: 6)
                                                .strokeBorder(
                                                    index == authVM.totpCode.count
                                                        ? Color.jarvisBlue.opacity(0.5)
                                                        : Color.jarvisBlue.opacity(0.15),
                                                    lineWidth: 1
                                                )
                                        }
                                }
                        }
                    }

                    // Hidden text field for input
                    TextField("", text: $authVM.totpCode)
                        .keyboardType(.numberPad)
                        .textContentType(.oneTimeCode)
                        .focused($isFocused)
                        .frame(width: 1, height: 1)
                        .opacity(0.01)
                        .onChange(of: authVM.totpCode) { _, newValue in
                            authVM.totpCode = String(newValue.prefix(6))
                                .filter { $0.isNumber }
                            if authVM.totpCode.count == 6 {
                                Task { await authVM.verifyTOTP() }
                            }
                        }
                }
                .onTapGesture { isFocused = true }
                .onAppear { isFocused = true }

                if let error = authVM.error {
                    Text(error)
                        .font(.system(size: 11, design: .monospaced))
                        .foregroundColor(.jarvisError)
                }

                // Verify button
                Button {
                    Task { await authVM.verifyTOTP() }
                } label: {
                    Text("VERIFY")
                        .font(.system(size: 13, weight: .medium, design: .monospaced))
                        .tracking(3)
                        .foregroundColor(.jarvisBlue)
                        .frame(maxWidth: .infinity)
                        .frame(height: 48)
                        .background {
                            HexCornerShape(cutSize: 8)
                                .fill(Color.jarvisBlue.opacity(0.08))
                                .overlay {
                                    HexCornerShape(cutSize: 8)
                                        .strokeBorder(Color.jarvisBlue.opacity(0.3), lineWidth: 1)
                                }
                        }
                }
                .disabled(authVM.totpCode.count != 6)
                .opacity(authVM.totpCode.count == 6 ? 1 : 0.5)
                .padding(.horizontal, 40)

                Spacer()

                Button {
                    authVM.needsTOTP = false
                    authVM.totpToken = nil
                } label: {
                    Text("CANCEL")
                        .font(.system(size: 10, weight: .medium, design: .monospaced))
                        .tracking(2)
                        .foregroundColor(.jarvisTextDim)
                }
                .padding(.bottom, 20)
            }
        }
    }
}
