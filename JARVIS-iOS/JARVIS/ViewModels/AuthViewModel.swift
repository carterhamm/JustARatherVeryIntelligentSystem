import SwiftUI
import AuthenticationServices

@MainActor
class AuthViewModel: ObservableObject {
    @Published var isAuthenticated = false
    @Published var isLoading = true
    @Published var error: String?
    @Published var user: UserResponse?

    // Multi-step login
    enum AuthStep { case identify, totp, authenticate }
    @Published var authStep: AuthStep = .identify
    @Published var identifier = ""
    @Published var lookupResult: LookupResponse?

    // TOTP flow
    @Published var needsTOTP = false
    @Published var totpToken: String?
    @Published var totpCode = ""
    private var pendingTotpCode: String?

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

    // Step 1: Lookup identifier
    func lookupUser() async {
        guard !identifier.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            error = "Enter your username or email"
            return
        }

        isLoading = true
        error = nil

        do {
            let result = try await auth.lookup(identifier: identifier)
            lookupResult = result

            if !result.exists {
                error = "No account found"
                isLoading = false
                return
            }

            if result.totpEnabled == true {
                withAnimation(.easeInOut(duration: 0.3)) {
                    authStep = .totp
                }
            } else {
                withAnimation(.easeInOut(duration: 0.3)) {
                    authStep = .authenticate
                }
            }
        } catch {
            self.error = "Connection failed"
        }

        isLoading = false
    }

    // Step 2: Submit TOTP and advance to passkey
    func submitTOTP() {
        guard totpCode.count == 6 else { return }
        pendingTotpCode = totpCode
        withAnimation(.easeInOut(duration: 0.3)) {
            authStep = .authenticate
        }
    }

    // Step 3: Trigger passkey auth
    func beginPasskeyAuth(anchor: ASPresentationAnchor) async {
        isLoading = true
        error = nil

        do {
            let challenge = try await auth.beginLogin(identifier: identifier)

            guard let challengeData = Data(base64URLEncoded: challenge.challenge),
                  let rpId = challenge.rpId else {
                error = "Invalid challenge from server"
                isLoading = false
                return
            }

            let provider = ASAuthorizationPlatformPublicKeyCredentialProvider(
                relyingPartyIdentifier: rpId
            )
            let request = provider.createCredentialAssertionRequest(
                challenge: challengeData
            )

            if let allowCredentials = challenge.allowCredentials {
                request.allowedCredentials = allowCredentials.compactMap { cred in
                    guard let credId = Data(base64URLEncoded: cred.id) else { return nil }
                    return ASAuthorizationPlatformPublicKeyCredentialDescriptor(
                        credentialID: credId
                    )
                }
            }

            let controller = ASAuthorizationController(authorizationRequests: [request])
            let delegate = PasskeyDelegate { [weak self] result in
                Task { @MainActor in
                    await self?.handlePasskeyResult(result)
                }
            }
            // Retain delegate
            self.passkeyDelegate = delegate
            controller.delegate = delegate
            controller.presentationContextProvider = PasskeyPresentationProvider(anchor: anchor)
            controller.performRequests()
        } catch {
            self.error = "Failed to start authentication"
            isLoading = false
        }
    }

    private var passkeyDelegate: PasskeyDelegate?

    private func handlePasskeyResult(_ result: Result<ASAuthorization, Error>) async {
        switch result {
        case .success(let authorization):
            guard let credential = authorization.credential
                    as? ASAuthorizationPlatformPublicKeyCredentialAssertion else {
                error = "Invalid credential"
                isLoading = false
                return
            }
            await completePasskeyLogin(credential: credential)

        case .failure(let err):
            if (err as? ASAuthorizationError)?.code == .canceled {
                // User cancelled — not an error
            } else {
                error = err.localizedDescription
            }
            isLoading = false
        }
        passkeyDelegate = nil
    }

    private func completePasskeyLogin(
        credential: ASAuthorizationPlatformPublicKeyCredentialAssertion
    ) async {
        do {
            let response = try await auth.completeLogin(
                identifier: identifier,
                credential: credential
            )

            if response.needsTotp == true, let token = response.totpToken {
                // Post-passkey TOTP: if we have a pending code, verify immediately
                if let code = pendingTotpCode {
                    let totpResponse = try await auth.verifyTOTP(
                        totpToken: token, code: code
                    )
                    user = totpResponse.user
                    isAuthenticated = true
                } else {
                    // Shouldn't happen in normal flow, but handle it
                    totpToken = token
                    needsTOTP = true
                    authStep = .totp
                }
            } else {
                user = response.user
                isAuthenticated = true
            }
        } catch {
            self.error = error.localizedDescription
        }

        isLoading = false
        pendingTotpCode = nil
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
            self.error = "Invalid code"
        }

        isLoading = false
        totpCode = ""
    }

    func goBack() {
        withAnimation(.easeInOut(duration: 0.3)) {
            switch authStep {
            case .identify:
                break
            case .totp:
                authStep = .identify
                totpCode = ""
            case .authenticate:
                if lookupResult?.totpEnabled == true {
                    authStep = .totp
                } else {
                    authStep = .identify
                }
            }
        }
        error = nil
    }

    func logout() async {
        await auth.logout()
        isAuthenticated = false
        user = nil
        needsTOTP = false
        totpToken = nil
        authStep = .identify
        identifier = ""
        lookupResult = nil
        totpCode = ""
    }
}

// MARK: - Passkey Delegate

private class PasskeyDelegate: NSObject, ASAuthorizationControllerDelegate {
    let completion: (Result<ASAuthorization, Error>) -> Void

    init(completion: @escaping (Result<ASAuthorization, Error>) -> Void) {
        self.completion = completion
    }

    func authorizationController(
        controller: ASAuthorizationController,
        didCompleteWithAuthorization authorization: ASAuthorization
    ) {
        completion(.success(authorization))
    }

    func authorizationController(
        controller: ASAuthorizationController,
        didCompleteWithError error: Error
    ) {
        completion(.failure(error))
    }
}

private class PasskeyPresentationProvider: NSObject,
    ASAuthorizationControllerPresentationContextProviding {
    let anchor: ASPresentationAnchor

    init(anchor: ASPresentationAnchor) {
        self.anchor = anchor
    }

    func presentationAnchor(for controller: ASAuthorizationController) -> ASPresentationAnchor {
        anchor
    }
}

// MARK: - Base64URL Decoding

extension Data {
    init?(base64URLEncoded string: String) {
        var base64 = string
            .replacingOccurrences(of: "-", with: "+")
            .replacingOccurrences(of: "_", with: "/")
        // Pad to multiple of 4
        while base64.count % 4 != 0 { base64.append("=") }
        self.init(base64Encoded: base64)
    }
}
