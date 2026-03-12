import Foundation
import AVFoundation
import SwiftUI
import WatchKit

@MainActor
class WatchVoiceManager: ObservableObject {
    @Published var isListening = false
    @Published var isProcessing = false
    @Published var isSpeaking = false
    @Published var audioLevel: Float = 0
    @Published var responseText = ""
    @Published var statusText = "TAP TO SPEAK"

    private var audioEngine = AVAudioEngine()
    private var recordingFile: AVAudioFile?
    private var recordingURL: URL?
    private var conversationId: String?
    private var silenceTimer: Timer?
    private var silenceDuration: TimeInterval = 0

    // Server config
    private let baseURL = "https://app.malibupoint.dev/api/v1"
    private var accessToken: String? {
        UserDefaults.standard.string(forKey: "jarvis_watch_token")
    }

    // MARK: - Start Listening (single tap)

    func startListening() {
        guard !isListening, !isProcessing else { return }

        WKInterfaceDevice.current().play(.start)

        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.record, mode: .measurement)
            try session.setActive(true)

            // Prepare recording file
            let url = FileManager.default.temporaryDirectory
                .appendingPathComponent("jarvis_\(UUID().uuidString).wav")
            recordingURL = url

            let inputNode = audioEngine.inputNode
            let recordingFormat = inputNode.outputFormat(forBus: 0)

            recordingFile = try AVAudioFile(
                forWriting: url,
                settings: recordingFormat.settings
            )

            inputNode.installTap(onBus: 0, bufferSize: 1024, format: recordingFormat) { [weak self] buffer, _ in
                // Write to file
                try? self?.recordingFile?.write(from: buffer)
                // Update audio level
                self?.processAudioLevel(buffer: buffer)
            }

            audioEngine.prepare()
            try audioEngine.start()

            isListening = true
            statusText = "LISTENING..."
            silenceDuration = 0

            // Silence detection — auto-stop after 2s of silence
            silenceTimer = Timer.scheduledTimer(withTimeInterval: 0.1, repeats: true) { [weak self] _ in
                Task { @MainActor in
                    guard let self = self, self.isListening else { return }
                    if self.audioLevel < 0.03 {
                        self.silenceDuration += 0.1
                        if self.silenceDuration > 2.0 {
                            self.stopAndSend()
                        }
                    } else {
                        self.silenceDuration = 0
                    }
                }
            }

            // Hard timeout at 30s
            Task {
                try? await Task.sleep(for: .seconds(30))
                if isListening { stopAndSend() }
            }

        } catch {
            statusText = "MIC ERROR"
        }
    }

    // MARK: - Stop & Send (tap again or auto-silence)

    func stopAndSend() {
        guard isListening else { return }

        audioEngine.stop()
        audioEngine.inputNode.removeTap(onBus: 0)
        recordingFile = nil
        silenceTimer?.invalidate()
        silenceTimer = nil
        isListening = false
        audioLevel = 0

        WKInterfaceDevice.current().play(.stop)

        guard let url = recordingURL else {
            statusText = "TAP TO SPEAK"
            return
        }

        // Check file has content
        guard let attrs = try? FileManager.default.attributesOfItem(atPath: url.path),
              let size = attrs[.size] as? Int, size > 1000 else {
            statusText = "TAP TO SPEAK"
            return
        }

        statusText = "PROCESSING..."
        isProcessing = true

        Task {
            await sendAudioToJARVIS(url)
            // Clean up temp file
            try? FileManager.default.removeItem(at: url)
        }
    }

    // MARK: - Send Audio to Backend

    private func sendAudioToJARVIS(_ audioURL: URL) async {
        guard let token = accessToken else {
            statusText = "NOT AUTHENTICATED"
            isProcessing = false
            return
        }

        do {
            let audioData = try Data(contentsOf: audioURL)

            // Use the voice/chat endpoint — sends audio, gets text response
            guard let url = URL(string: "\(baseURL)/voice/chat") else { return }

            let boundary = UUID().uuidString
            var request = URLRequest(url: url)
            request.httpMethod = "POST"
            request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")

            var body = Data()

            // Audio file
            body.append("--\(boundary)\r\n")
            body.append("Content-Disposition: form-data; name=\"audio\"; filename=\"recording.wav\"\r\n")
            body.append("Content-Type: audio/wav\r\n\r\n")
            body.append(audioData)
            body.append("\r\n")

            // Conversation ID
            if let convId = conversationId {
                body.append("--\(boundary)\r\n")
                body.append("Content-Disposition: form-data; name=\"conversation_id\"\r\n\r\n")
                body.append(convId)
                body.append("\r\n")
            }

            body.append("--\(boundary)--\r\n")
            request.httpBody = body

            let (data, response) = try await URLSession.shared.data(for: request)

            guard let httpResp = response as? HTTPURLResponse,
                  (200...299).contains(httpResp.statusCode) else {
                // Fallback: try text chat if voice endpoint fails
                statusText = "VOICE UNAVAILABLE"
                isProcessing = false
                return
            }

            struct VoiceResp: Codable {
                let transcription: String
                let response_text: String
                let conversation_id: String
            }

            let voiceResp = try JSONDecoder().decode(VoiceResp.self, from: data)
            conversationId = voiceResp.conversation_id
            responseText = voiceResp.response_text

            isProcessing = false
            isSpeaking = true
            statusText = "JARVIS"

            WKInterfaceDevice.current().play(.success)

            // Hold response on screen
            let wordCount = voiceResp.response_text.split(separator: " ").count
            let readTime = max(3.0, Double(wordCount) / 3.0)
            try? await Task.sleep(for: .seconds(readTime))

            isSpeaking = false
            statusText = "TAP TO SPEAK"

        } catch {
            statusText = "CONNECTION ERROR"
            isProcessing = false
        }
    }

    // MARK: - Audio Level Processing

    private func processAudioLevel(buffer: AVAudioPCMBuffer) {
        guard let channelData = buffer.floatChannelData else { return }
        let frames = buffer.frameLength
        var sum: Float = 0
        for i in 0..<Int(frames) {
            let sample = channelData[0][i]
            sum += sample * sample
        }
        let rms = sqrt(sum / Float(frames))
        let level = max(0, min(1, rms * 8))

        Task { @MainActor in
            self.audioLevel = level
        }
    }
}

// MARK: - Data Helper

private extension Data {
    mutating func append(_ string: String) {
        if let data = string.data(using: .utf8) {
            append(data)
        }
    }
}
