import Foundation

#if canImport(FoundationModels)
import FoundationModels
#endif

actor IntentDetector {
    static let shared = IntentDetector()

    func classify(_ message: String) async -> (intent: String, entity: String?) {
        // Try Foundation Models on iOS 26+ for smart classification
        if #available(iOS 26, *) {
            if let result = await classifyWithFoundationModels(message) {
                return result
            }
        }

        // Fallback: keyword-based classification
        return classifyKeyword(message)
    }

    @available(iOS 26, *)
    private func classifyWithFoundationModels(_ message: String) async -> (intent: String, entity: String?)? {
        #if canImport(FoundationModels)
        do {
            let session = LanguageModelSession(
                instructions: "Classify intent: music, navigation, weather, calendar, reminder, search, or general. Reply ONLY with the category name."
            )
            let response = try await session.respond(to: message)
            let text = String(describing: response).lowercased().trimmingCharacters(in: .whitespacesAndNewlines)
            let validIntents = ["music", "navigation", "weather", "calendar", "reminder", "search", "general"]
            let intent = validIntents.first(where: { text.contains($0) }) ?? "general"
            return (intent: intent, entity: nil)
        } catch {
            return nil // Fall through to keyword
        }
        #else
        return nil
        #endif
    }

    private func classifyKeyword(_ message: String) -> (intent: String, entity: String?) {
        let lower = message.lowercased()
        if lower.contains("play ") || lower.contains("music") || lower.contains("song") || lower.contains("pause") || lower.contains("skip") {
            return (intent: "music", entity: nil)
        }
        if lower.contains("weather") || lower.contains("temperature") || lower.contains("forecast") {
            return (intent: "weather", entity: nil)
        }
        if lower.contains("navigate") || lower.contains("directions") || lower.contains("how far") || lower.contains("route") {
            return (intent: "navigation", entity: nil)
        }
        if lower.contains("remind") || lower.contains("reminder") {
            return (intent: "reminder", entity: nil)
        }
        if lower.contains("calendar") || lower.contains("schedule") || lower.contains("meeting") {
            return (intent: "calendar", entity: nil)
        }
        return (intent: "general", entity: nil)
    }
}
