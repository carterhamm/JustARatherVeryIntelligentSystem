import SwiftUI
import AuthenticationServices

@MainActor
class AuthViewModel: ObservableObject {
    @Published var isAuthenticated = false
    @Published var isLoading = true
    @Published var error: String?
    @Published var user: UserResponse?

    // TOTP flow
    @Published var needsTOTP = false
    @Published var totpToken: String?
    @Published var totpCode = ""

    // Login
    @Published var identifier = ""

    private let auth = AuthService.shared

    func restoreSession() async {
        isLoading = true
        isAuthenticated = await auth.restoreSession()
        if isAuthenticated {
            do {
                user = try await auth.getProfile()
            } catch {}
        }
        isLoading = false
    }

    func handlePasskeyAuth(_ authorization: ASAuthorization) async {
        guard let credential = authorization.credential as? ASAuthorizationPlatformPublicKeyCredentialAssertion else {
            error = "Invalid credential type"
            return
        }

        isLoading = true
        error = nil

        do {
            let response = try await auth.loginWithPasskey(
                identifier: identifier,
                credential: credential
            )

            if response.needsTotp == true {
                totpToken = response.totpToken
                needsTOTP = true
            } else {
                user = response.user
                isAuthenticated = true
            }
        } catch {
            self.error = error.localizedDescription
        }

        isLoading = false
    }

    func verifyTOTP() async {
        guard let token = totpToken, !totpCode.isEmpty else { return }

        isLoading = true
        error = nil

        do {
            let response = try await auth.verifyTOTP(totpToken: token, code: totpCode)
            user = response.user
            isAuthenticated = true
            needsTOTP = false
        } catch {
            self.error = "Invalid TOTP code"
        }

        isLoading = false
        totpCode = ""
    }

    func logout() async {
        await auth.logout()
        isAuthenticated = false
        user = nil
        needsTOTP = false
        totpToken = nil
    }
}
