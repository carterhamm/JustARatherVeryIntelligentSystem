import Foundation
import AuthenticationServices

actor AuthService {
    static let shared = AuthService()

    private let api = APIClient.shared

    func checkSetupStatus() async throws -> Bool {
        let response: SetupStatusResponse = try await api.request(
            JARVISConfig.Auth.setupStatus, authenticated: false
        )
        return response.setupComplete
    }

    func lookup(identifier: String) async throws -> LookupResponse {
        struct Req: Encodable { let identifier: String }
        return try await api.request(
            JARVISConfig.Auth.lookup,
            method: "POST",
            body: Req(identifier: identifier),
            authenticated: false
        )
    }

    func loginWithPasskey(
        identifier: String,
        credential: ASAuthorizationPlatformPublicKeyCredentialAssertion
    ) async throws -> AuthResponse {
        // Step 1: Begin login to get challenge
        struct BeginReq: Encodable { let identifier: String }
        let _: [String: AnyCodable] = try await api.request(
            JARVISConfig.Auth.loginBegin,
            method: "POST",
            body: BeginReq(identifier: identifier),
            authenticated: false
        )

        // Step 2: Complete login with credential
        let credentialData = PasskeyCredentialData(
            id: credential.credentialID.base64URLEncodedString(),
            rawId: credential.credentialID.base64URLEncodedString(),
            response: PasskeyAssertionResponse(
                clientDataJSON: credential.rawClientDataJSON.base64URLEncodedString(),
                authenticatorData: credential.rawAuthenticatorData.base64URLEncodedString(),
                signature: credential.signature.base64URLEncodedString()
            ),
            type: "public-key"
        )

        struct CompleteReq: Encodable {
            let identifier: String
            let credential: PasskeyCredentialData
        }

        let response: AuthResponse = try await api.request(
            JARVISConfig.Auth.loginComplete,
            method: "POST",
            body: CompleteReq(identifier: identifier, credential: credentialData),
            authenticated: false
        )

        if response.needsTotp == true {
            return response
        }

        await api.setTokens(access: response.accessToken, refresh: response.refreshToken)

        if let user = response.user {
            try? await KeychainService.shared.save(user.id, for: .userId)
            try? await KeychainService.shared.save(user.username, for: .username)
            try? await KeychainService.shared.save(user.email, for: .email)
        }

        return response
    }

    func verifyTOTP(totpToken: String, code: String) async throws -> AuthResponse {
        struct Req: Encodable {
            let totpToken: String
            let code: String
            enum CodingKeys: String, CodingKey {
                case totpToken = "totp_token"
                case code
            }
        }

        let response: AuthResponse = try await api.request(
            JARVISConfig.Auth.totpVerify,
            method: "POST",
            body: Req(totpToken: totpToken, code: code),
            authenticated: false
        )

        await api.setTokens(access: response.accessToken, refresh: response.refreshToken)

        if let user = response.user {
            try? await KeychainService.shared.save(user.id, for: .userId)
            try? await KeychainService.shared.save(user.username, for: .username)
            try? await KeychainService.shared.save(user.email, for: .email)
        }

        return response
    }

    // Password-based login fallback
    func loginWithPassword(username: String, password: String) async throws -> AuthResponse {
        struct Req: Encodable {
            let username: String
            let password: String
        }

        // Try the standard login endpoint
        let response: AuthResponse = try await api.request(
            JARVISConfig.Auth.loginComplete,
            method: "POST",
            body: Req(username: username, password: password),
            authenticated: false
        )

        if response.needsTotp != true {
            await api.setTokens(access: response.accessToken, refresh: response.refreshToken)
        }

        return response
    }

    func getProfile() async throws -> UserResponse {
        try await api.request(JARVISConfig.Auth.me)
    }

    func getPreferences() async throws -> UserPreferences {
        try await api.request(JARVISConfig.Auth.preferences)
    }

    func logout() async {
        await api.clearTokens()
    }

    func restoreSession() async -> Bool {
        await api.loadTokens()
        guard await api.isAuthenticated else { return false }

        do {
            let _: UserResponse = try await api.request(JARVISConfig.Auth.me)
            return true
        } catch {
            return false
        }
    }
}

// MARK: - Passkey Support Types

struct PasskeyCredentialData: Encodable {
    let id: String
    let rawId: String
    let response: PasskeyAssertionResponse
    let type: String
}

struct PasskeyAssertionResponse: Encodable {
    let clientDataJSON: String
    let authenticatorData: String
    let signature: String
}

// MARK: - Base64URL

extension Data {
    func base64URLEncodedString() -> String {
        base64EncodedString()
            .replacingOccurrences(of: "+", with: "-")
            .replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: "=", with: "")
    }
}

// MARK: - AnyCodable for dynamic JSON

struct AnyCodable: Codable {
    let value: Any

    init(_ value: Any) { self.value = value }

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let str = try? container.decode(String.self) { value = str }
        else if let int = try? container.decode(Int.self) { value = int }
        else if let double = try? container.decode(Double.self) { value = double }
        else if let bool = try? container.decode(Bool.self) { value = bool }
        else if let dict = try? container.decode([String: AnyCodable].self) { value = dict }
        else if let arr = try? container.decode([AnyCodable].self) { value = arr }
        else { value = NSNull() }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        if let str = value as? String { try container.encode(str) }
        else if let int = value as? Int { try container.encode(int) }
        else if let double = value as? Double { try container.encode(double) }
        else if let bool = value as? Bool { try container.encode(bool) }
        else { try container.encodeNil() }
    }
}
