import WidgetKit
import SwiftUI

// MARK: - Widget Definition

struct JARVISStatusWidget: Widget {
    let kind = "JARVISStatus"

    var body: some WidgetConfiguration {
        StaticConfiguration(kind: kind, provider: StatusProvider()) { entry in
            StatusWidgetView(entry: entry)
        }
        .configurationDisplayName("JARVIS Status")
        .description("Shows JARVIS system status and latest insight")
        .supportedFamilies([.systemSmall, .systemMedium, .accessoryRectangular])
    }
}

// MARK: - Timeline Entry

struct StatusEntry: TimelineEntry {
    let date: Date
    let status: String
    let latestInsight: String
    let learningCycles: Int
}

// MARK: - Timeline Provider

struct StatusProvider: TimelineProvider {
    func placeholder(in context: Context) -> StatusEntry {
        StatusEntry(
            date: .now,
            status: "HEALTHY",
            latestInsight: "All systems nominal, sir.",
            learningCycles: 48
        )
    }

    func getSnapshot(in context: Context, completion: @escaping (StatusEntry) -> Void) {
        completion(placeholder(in: context))
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<StatusEntry>) -> Void) {
        Task {
            let entry = await fetchStatus()
            // Refresh every 15 minutes
            let nextUpdate = Date().addingTimeInterval(900)
            let timeline = Timeline(entries: [entry], policy: .after(nextUpdate))
            completion(timeline)
        }
    }

    private func fetchStatus() async -> StatusEntry {
        guard let url = URL(string: "https://app.malibupoint.dev/health") else {
            return StatusEntry(date: .now, status: "OFFLINE", latestInsight: "Unable to reach server.", learningCycles: 0)
        }

        do {
            let (data, response) = try await URLSession.shared.data(from: url)

            guard let httpResponse = response as? HTTPURLResponse,
                  (200...299).contains(httpResponse.statusCode) else {
                return StatusEntry(date: .now, status: "DEGRADED", latestInsight: "Non-200 response received.", learningCycles: 0)
            }

            if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               let status = json["status"] as? String {
                return StatusEntry(
                    date: .now,
                    status: status.uppercased(),
                    latestInsight: "Systems nominal, sir.",
                    learningCycles: 48
                )
            }
        } catch {
            // Network error
        }

        return StatusEntry(date: .now, status: "OFFLINE", latestInsight: "Connection lost.", learningCycles: 0)
    }
}

// MARK: - Widget Views

struct StatusWidgetView: View {
    let entry: StatusEntry
    @Environment(\.widgetFamily) var family

    var body: some View {
        switch family {
        case .systemSmall:
            smallView
        case .systemMedium:
            mediumView
        case .accessoryRectangular:
            rectangularView
        default:
            smallView
        }
    }

    // MARK: Small

    private var smallView: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 4) {
                Circle()
                    .fill(statusColor)
                    .frame(width: 6, height: 6)
                Text("JARVIS")
                    .font(.system(size: 10, weight: .bold, design: .monospaced))
                    .foregroundColor(WidgetColors.cyan)
            }

            Spacer()

            Text(entry.status)
                .font(.system(size: 14, weight: .bold, design: .monospaced))
                .foregroundColor(.white)

            Text("\(entry.learningCycles) cycles today")
                .font(.system(size: 8, design: .monospaced))
                .foregroundColor(WidgetColors.textDim)

            Text(entry.date, style: .time)
                .font(.system(size: 7, design: .monospaced))
                .foregroundColor(WidgetColors.textDim.opacity(0.6))
        }
        .padding(12)
        .containerBackground(for: .widget) {
            WidgetColors.background
        }
    }

    // MARK: Medium

    private var mediumView: some View {
        HStack(spacing: 0) {
            // Left panel — status
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 4) {
                    Circle()
                        .fill(statusColor)
                        .frame(width: 6, height: 6)
                    Text("JARVIS")
                        .font(.system(size: 10, weight: .bold, design: .monospaced))
                        .foregroundColor(WidgetColors.cyan)
                }

                Spacer()

                Text(entry.status)
                    .font(.system(size: 14, weight: .bold, design: .monospaced))
                    .foregroundColor(.white)

                Text("\(entry.learningCycles) cycles today")
                    .font(.system(size: 8, design: .monospaced))
                    .foregroundColor(WidgetColors.textDim)
            }
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)

            // Divider
            Rectangle()
                .fill(WidgetColors.cyan.opacity(0.15))
                .frame(width: 0.5)
                .padding(.vertical, 12)

            // Right panel — insight
            VStack(alignment: .leading, spacing: 4) {
                Text("LATEST")
                    .font(.system(size: 8, weight: .bold, design: .monospaced))
                    .foregroundColor(WidgetColors.cyan.opacity(0.6))
                    .tracking(1.2)

                Text(entry.latestInsight)
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundColor(.white.opacity(0.8))
                    .lineLimit(3)

                Spacer()

                Text(entry.date, style: .time)
                    .font(.system(size: 7, design: .monospaced))
                    .foregroundColor(WidgetColors.textDim.opacity(0.6))
            }
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .containerBackground(for: .widget) {
            WidgetColors.background
        }
    }

    // MARK: Lock Screen (Rectangular)

    private var rectangularView: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(spacing: 4) {
                Image(systemName: "cpu")
                    .font(.system(size: 8))
                Text("JARVIS")
                    .font(.system(size: 10, weight: .bold, design: .monospaced))
            }
            Text(entry.status)
                .font(.system(size: 12, weight: .bold, design: .monospaced))
        }
    }

    // MARK: Helpers

    private var statusColor: Color {
        switch entry.status {
        case "HEALTHY": return WidgetColors.online
        case "DEGRADED": return WidgetColors.warning
        default: return WidgetColors.error
        }
    }
}

// MARK: - Preview

#Preview("Small", as: .systemSmall) {
    JARVISStatusWidget()
} timeline: {
    StatusEntry(date: .now, status: "HEALTHY", latestInsight: "Systems nominal, sir.", learningCycles: 48)
    StatusEntry(date: .now, status: "OFFLINE", latestInsight: "Connection lost.", learningCycles: 0)
}

#Preview("Medium", as: .systemMedium) {
    JARVISStatusWidget()
} timeline: {
    StatusEntry(date: .now, status: "HEALTHY", latestInsight: "Morning briefing delivered. Three calendar events today.", learningCycles: 48)
}
