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

    private var audioEngine = AVAudioEngine()
    private var recognitionRequest: SFSpeechAudioBufferRecognitionRequest?
    private var recognitionTask: SFSpeechRecognitionTask?
    private let speechRecognizer = SFSpeechRecognizer(locale: Locale(identifier: "en-US"))

    private var audioRecorder: AVAudioRecorder?
    private var recordingURL: URL?
    private var levelTimer: Timer?

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

    func stopListening() -> String {
        guard isRecording else { return transcribedText }

        audioEngine.stop()
        audioEngine.inputNode.removeTap(onBus: 0)
        recognitionRequest?.endAudio()
        recognitionTask?.cancel()
        recognitionRequest = nil
        recognitionTask = nil
        isRecording = false

        let text = transcribedText
        transcribedText = ""
        return text
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
                // Normalize from -160..0 to 0..1
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

    private var audioPlayer: AVAudioPlayer?

    func speak(_ text: String) async {
        // Use system TTS as fallback
        let synthesizer = AVSpeechSynthesizer()
        let utterance = AVSpeechUtterance(string: text)
        utterance.voice = AVSpeechSynthesisVoice(language: "en-GB")
        utterance.rate = 0.52
        utterance.pitchMultiplier = 0.95

        do {
            try AVAudioSession.sharedInstance().setCategory(.playback)
            try AVAudioSession.sharedInstance().setActive(true)
        } catch {}

        synthesizer.speak(utterance)
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
        let level = max(0, min(1, rms * 5))

        Task { @MainActor in
            self.audioLevel = level
        }
    }
}
