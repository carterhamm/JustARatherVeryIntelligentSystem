import Foundation

actor APIClient {
    static let shared = APIClient()

    private let session: URLSession
    private let decoder: JSONDecoder

    init() {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 30
        config.timeoutIntervalForResource = 120
        self.session = URLSession(configuration: config)
        self.decoder = JSONDecoder()
    }

    // MARK: - Token Management

    private var accessToken: String?
    private var refreshToken: String?

    func setTokens(access: String, refresh: String) async {
        self.accessToken = access
        self.refreshToken = refresh
        try? await KeychainService.shared.save(access, for: .accessToken)
        try? await KeychainService.shared.save(refresh, for: .refreshToken)
    }

    func loadTokens() async {
        self.accessToken = await KeychainService.shared.load(.accessToken)
        self.refreshToken = await KeychainService.shared.load(.refreshToken)
    }

    func clearTokens() async {
        self.accessToken = nil
        self.refreshToken = nil
        await KeychainService.shared.clearAll()
    }

    func getAccessToken() -> String? { accessToken }

    var isAuthenticated: Bool { accessToken != nil }

    // MARK: - Requests

    func request<T: Decodable>(
        _ url: String,
        method: String = "GET",
        body: (any Encodable)? = nil,
        authenticated: Bool = true
    ) async throws -> T {
        guard let url = URL(string: url) else {
            throw JARVISError.invalidURL
        }

        var req = URLRequest(url: url)
        req.httpMethod = method
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.setValue("application/json", forHTTPHeaderField: "Accept")

        if authenticated, let token = accessToken {
            req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }

        if let body = body {
            req.httpBody = try JSONEncoder().encode(body)
        }

        let (data, response) = try await session.data(for: req)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw JARVISError.invalidResponse
        }

        if httpResponse.statusCode == 401, authenticated {
            if try await attemptTokenRefresh() {
                return try await request(
                    url.absoluteString, method: method, body: body, authenticated: true
                )
            }
            throw JARVISError.unauthorized
        }

        guard (200...299).contains(httpResponse.statusCode) else {
            if let apiError = try? decoder.decode(APIError.self, from: data) {
                throw JARVISError.api(apiError.detail, httpResponse.statusCode)
            }
            throw JARVISError.httpError(httpResponse.statusCode)
        }

        return try decoder.decode(T.self, from: data)
    }

    func requestVoid(
        _ url: String,
        method: String = "GET",
        body: (any Encodable)? = nil,
        authenticated: Bool = true
    ) async throws {
        guard let url = URL(string: url) else {
            throw JARVISError.invalidURL
        }

        var req = URLRequest(url: url)
        req.httpMethod = method
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")

        if authenticated, let token = accessToken {
            req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }

        if let body = body {
            req.httpBody = try JSONEncoder().encode(body)
        }

        let (_, response) = try await session.data(for: req)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw JARVISError.invalidResponse
        }

        guard (200...299).contains(httpResponse.statusCode) else {
            throw JARVISError.httpError(httpResponse.statusCode)
        }
    }

    // MARK: - SSE Streaming

    nonisolated func streamRequest(
        _ url: String,
        body: some Encodable
    ) -> AsyncThrowingStream<StreamChunk, Error> {
        AsyncThrowingStream { continuation in
            Task {
                guard let url = URL(string: url) else {
                    continuation.finish(throwing: JARVISError.invalidURL)
                    return
                }

                var req = URLRequest(url: url)
                req.httpMethod = "POST"
                req.setValue("application/json", forHTTPHeaderField: "Content-Type")
                req.setValue("text/event-stream", forHTTPHeaderField: "Accept")

                if let token = await self.accessToken {
                    req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
                }

                req.httpBody = try? JSONEncoder().encode(body)

                do {
                    let (bytes, response) = try await self.session.bytes(for: req)

                    guard let httpResponse = response as? HTTPURLResponse,
                          (200...299).contains(httpResponse.statusCode) else {
                        continuation.finish(throwing: JARVISError.invalidResponse)
                        return
                    }

                    for try await line in bytes.lines {
                        guard line.hasPrefix("data: ") else { continue }
                        let jsonStr = String(line.dropFirst(6))
                        guard let data = jsonStr.data(using: .utf8),
                              let chunk = try? JSONDecoder().decode(StreamChunk.self, from: data)
                        else { continue }

                        continuation.yield(chunk)

                        if chunk.done == true || chunk.type == "end" {
                            continuation.finish()
                            return
                        }
                    }

                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
        }
    }

    // MARK: - Multipart Upload

    func uploadMultipart<T: Decodable>(
        _ urlString: String,
        fileData: Data,
        fileName: String,
        mimeType: String,
        fieldName: String = "audio",
        additionalFields: [String: String] = [:]
    ) async throws -> T {
        guard let url = URL(string: urlString) else {
            throw JARVISError.invalidURL
        }

        let boundary = UUID().uuidString
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue(
            "multipart/form-data; boundary=\(boundary)",
            forHTTPHeaderField: "Content-Type"
        )

        if let token = accessToken {
            req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }

        var body = Data()

        // File field
        body.append("--\(boundary)\r\n")
        body.append("Content-Disposition: form-data; name=\"\(fieldName)\"; filename=\"\(fileName)\"\r\n")
        body.append("Content-Type: \(mimeType)\r\n\r\n")
        body.append(fileData)
        body.append("\r\n")

        // Additional fields
        for (key, value) in additionalFields {
            body.append("--\(boundary)\r\n")
            body.append("Content-Disposition: form-data; name=\"\(key)\"\r\n\r\n")
            body.append(value)
            body.append("\r\n")
        }

        body.append("--\(boundary)--\r\n")
        req.httpBody = body

        let (data, response) = try await session.data(for: req)

        guard let httpResponse = response as? HTTPURLResponse,
              (200...299).contains(httpResponse.statusCode) else {
            throw JARVISError.invalidResponse
        }

        return try decoder.decode(T.self, from: data)
    }

    // MARK: - Token Refresh

    private func attemptTokenRefresh() async throws -> Bool {
        guard let refresh = refreshToken else { return false }

        struct RefreshRequest: Codable {
            let refreshToken: String
            enum CodingKeys: String, CodingKey {
                case refreshToken = "refresh_token"
            }
        }

        guard let url = URL(string: JARVISConfig.Auth.refresh) else { return false }

        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try JSONEncoder().encode(RefreshRequest(refreshToken: refresh))

        let (data, response) = try await session.data(for: req)

        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else {
            await clearTokens()
            return false
        }

        struct TokenResponse: Codable {
            let accessToken: String
            let refreshToken: String
            enum CodingKeys: String, CodingKey {
                case accessToken = "access_token"
                case refreshToken = "refresh_token"
            }
        }

        guard let tokens = try? decoder.decode(TokenResponse.self, from: data) else {
            return false
        }

        await setTokens(access: tokens.accessToken, refresh: tokens.refreshToken)
        return true
    }
}

// MARK: - Errors

enum JARVISError: LocalizedError {
    case invalidURL
    case invalidResponse
    case unauthorized
    case httpError(Int)
    case api(String, Int)
    case noData
    case decodingError

    var errorDescription: String? {
        switch self {
        case .invalidURL: return "Invalid URL"
        case .invalidResponse: return "Invalid server response"
        case .unauthorized: return "Authentication required"
        case .httpError(let code): return "HTTP error \(code)"
        case .api(let msg, _): return msg
        case .noData: return "No data received"
        case .decodingError: return "Failed to decode response"
        }
    }
}

// MARK: - Data Helpers

extension Data {
    mutating func append(_ string: String) {
        if let data = string.data(using: .utf8) {
            append(data)
        }
    }
}
