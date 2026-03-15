import Foundation
import AVFoundation
import Speech

@MainActor
class VoiceService: NSObject, ObservableObject {
    static let shared = VoiceService()

    @Published var isRecording = false
    @Published var isProcessing = false
    @Published var audioLevel: Float = 0
    @Published var transcribedText = ""
    @Published var isSpeaking = false

    private var audioEngine = AVAudioEngine()
    private var recognitionRequest: SFSpeechAudioBufferRecognitionRequest?
    private var recognitionTask: SFSpeechRecognitionTask?
    private let speechRecognizer = SFSpeechRecognizer(locale: Locale(identifier: "en-US"))

    private var audioRecorder: AVAudioRecorder?
    private var recordingURL: URL?
    private var levelTimer: Timer?

    // VAD (Voice Activity Detection)
    private var silenceTimer: Timer?
    private let silenceThreshold: Float = 0.01
    private let silenceDuration: TimeInterval = 1.5
    private var hasDetectedSpeech = false

    // Callback when silence triggers auto-stop
    var onSilenceDetected: ((String) -> Void)?

    // TTS playback
    private var audioPlayer: AVAudioPlayer?
    private var speechSynthesizer: AVSpeechSynthesizer?

    override init() {
        super.init()
    }

    // MARK: - Permissions

    func requestPermissions() async -> Bool {
        let speechAuth = await withCheckedContinuation { cont in
            SFSpeechRecognizer.requestAuthorization { status in
                cont.resume(returning: status == .authorized)
            }
        }

        let micAuth: Bool
        if #available(iOS 17.0, *) {
            micAuth = await AVAudioApplication.requestRecordPermission()
        } else {
            micAuth = await withCheckedContinuation { cont in
                AVAudioSession.sharedInstance().requestRecordPermission { granted in
                    cont.resume(returning: granted)
                }
            }
        }

        return speechAuth && micAuth
    }

    // MARK: - Recording with Speech Recognition

    func startListening() {
        guard !isRecording else { return }

        // Reset state
        transcribedText = ""
        hasDetectedSpeech = false
        silenceTimer?.invalidate()
        silenceTimer = nil

        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.record, mode: .measurement)
            try session.setActive(true, options: .notifyOthersOnDeactivation)

            recognitionRequest = SFSpeechAudioBufferRecognitionRequest()
            guard let recognitionRequest = recognitionRequest else { return }
            recognitionRequest.shouldReportPartialResults = true

            let inputNode = audioEngine.inputNode
            let recordingFormat = inputNode.outputFormat(forBus: 0)

            inputNode.installTap(onBus: 0, bufferSize: 1024, format: recordingFormat) { [weak self] buffer, _ in
                self?.recognitionRequest?.append(buffer)
                self?.processAudioLevel(buffer: buffer)
            }

            recognitionTask = speechRecognizer?.recognitionTask(with: recognitionRequest) { [weak self] result, error in
                Task { @MainActor in
                    if let result = result {
                        self?.transcribedText = result.bestTranscription.formattedString
                        if !result.bestTranscription.formattedString.isEmpty {
                            self?.hasDetectedSpeech = true
                        }
                    }
                    if error != nil || result?.isFinal == true {
                        // Recognition ended
                    }
                }
            }

            audioEngine.prepare()
            try audioEngine.start()

            isRecording = true
        } catch {
            print("Failed to start recording: \(error)")
        }
    }

    @discardableResult
    func stopListening() -> String {
        guard isRecording else { return transcribedText }

        // Cancel silence timer
        silenceTimer?.invalidate()
        silenceTimer = nil

        audioEngine.stop()
        audioEngine.inputNode.removeTap(onBus: 0)
        recognitionRequest?.endAudio()
        recognitionTask?.cancel()
        recognitionRequest = nil
        recognitionTask = nil
        isRecording = false
        hasDetectedSpeech = false

        let text = transcribedText
        return text
    }

    // MARK: - Stop TTS Playback

    func stopSpeaking() {
        audioPlayer?.stop()
        audioPlayer = nil
        speechSynthesizer?.stopSpeaking(at: .immediate)
        speechSynthesizer = nil
        isSpeaking = false
    }

    // MARK: - Direct Audio Recording (for voice/chat endpoint)

    func startRecording() throws -> URL {
        let session = AVAudioSession.sharedInstance()
        try session.setCategory(.record, mode: .measurement)
        try session.setActive(true)

        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("jarvis_recording_\(UUID().uuidString).m4a")

        let settings: [String: Any] = [
            AVFormatIDKey: Int(kAudioFormatMPEG4AAC),
            AVSampleRateKey: 44100.0,
            AVNumberOfChannelsKey: 1,
            AVEncoderAudioQualityKey: AVAudioQuality.high.rawValue
        ]

        audioRecorder = try AVAudioRecorder(url: url, settings: settings)
        audioRecorder?.isMeteringEnabled = true
        audioRecorder?.record()
        recordingURL = url
        isRecording = true

        // Level monitoring
        levelTimer = Timer.scheduledTimer(withTimeInterval: 0.05, repeats: true) { [weak self] _ in
            Task { @MainActor in
                self?.audioRecorder?.updateMeters()
                let level = self?.audioRecorder?.averagePower(forChannel: 0) ?? -160
                self?.audioLevel = max(0, min(1, (level + 50) / 50))
            }
        }

        return url
    }

    func stopRecording() -> URL? {
        audioRecorder?.stop()
        levelTimer?.invalidate()
        levelTimer = nil
        isRecording = false
        audioLevel = 0
        return recordingURL
    }

    // MARK: - Voice Chat (send audio, get response)

    func voiceChat(audioURL: URL, conversationId: String? = nil) async throws -> VoiceChatResponse {
        let data = try Data(contentsOf: audioURL)
        var fields: [String: String] = [:]
        if let convId = conversationId {
            fields["conversation_id"] = convId
        }

        return try await APIClient.shared.uploadMultipart(
            JARVISConfig.Voice.voiceChat,
            fileData: data,
            fileName: "recording.m4a",
            mimeType: "audio/mp4",
            fieldName: "audio",
            additionalFields: fields
        )
    }

    // MARK: - TTS Playback

    func speak(_ text: String) async {
        // Try ElevenLabs via backend first, fall back to system TTS
        do {
            let audioData = try await synthesizeViaBackend(text: text)
            try await playAudioData(audioData)
            return
        } catch {
            print("Backend TTS failed, falling back to system: \(error)")
        }

        // System TTS fallback
        await speakWithSystemTTS(text)
    }

    private func synthesizeViaBackend(text: String) async throws -> Data {
        guard let url = URL(string: JARVISConfig.Voice.synthesize) else {
            throw JARVISError.invalidURL
        }

        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")

        if let token = await APIClient.shared.getAccessToken() {
            req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }

        struct SynthesizeBody: Codable {
            let text: String
        }
        req.httpBody = try JSONEncoder().encode(SynthesizeBody(text: text))

        let (data, response) = try await URLSession.shared.data(for: req)

        guard let httpResponse = response as? HTTPURLResponse,
              (200...299).contains(httpResponse.statusCode) else {
            throw JARVISError.invalidResponse
        }

        guard !data.isEmpty else {
            throw JARVISError.noData
        }

        return data
    }

    private func playAudioData(_ data: Data) async throws {
        try AVAudioSession.sharedInstance().setCategory(.playback)
        try AVAudioSession.sharedInstance().setActive(true)

        let player = try AVAudioPlayer(data: data)
        self.audioPlayer = player
        self.isSpeaking = true
        player.play()

        // Wait for playback to finish
        while player.isPlaying {
            try await Task.sleep(for: .milliseconds(100))
        }
        self.isSpeaking = false
        self.audioPlayer = nil
    }

    private func speakWithSystemTTS(_ text: String) async {
        let synthesizer = AVSpeechSynthesizer()
        self.speechSynthesizer = synthesizer
        let utterance = AVSpeechUtterance(string: text)
        utterance.voice = AVSpeechSynthesisVoice(language: "en-GB")
        utterance.rate = 0.52
        utterance.pitchMultiplier = 0.95

        do {
            try AVAudioSession.sharedInstance().setCategory(.playback)
            try AVAudioSession.sharedInstance().setActive(true)
        } catch {}

        isSpeaking = true
        synthesizer.speak(utterance)

        // Wait for system TTS to finish — poll since we don't use delegate
        while synthesizer.isSpeaking {
            try? await Task.sleep(for: .milliseconds(100))
        }
        isSpeaking = false
        self.speechSynthesizer = nil
    }

    // MARK: - Audio Level Processing + VAD

    private func processAudioLevel(buffer: AVAudioPCMBuffer) {
        guard let channelData = buffer.floatChannelData else { return }
        let frames = buffer.frameLength
        var sum: Float = 0
        for i in 0..<Int(frames) {
            let sample = channelData[0][i]
            sum += sample * sample
        }
        let rms = sqrt(sum / Float(frames))
        let level = max(0, min(1, rms * 5))

        Task { @MainActor in
            self.audioLevel = level

            // VAD: only trigger silence detection after speech has been detected
            if rms < self.silenceThreshold {
                if self.hasDetectedSpeech && self.silenceTimer == nil {
                    self.silenceTimer = Timer.scheduledTimer(withTimeInterval: self.silenceDuration, repeats: false) { [weak self] _ in
                        Task { @MainActor in
                            guard let self = self, self.isRecording else { return }
                            let text = self.stopListening()
                            self.onSilenceDetected?(text)
                        }
                    }
                }
            } else {
                self.silenceTimer?.invalidate()
                self.silenceTimer = nil
            }
        }
    }
}
