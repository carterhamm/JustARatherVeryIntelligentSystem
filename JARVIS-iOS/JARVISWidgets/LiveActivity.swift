import ActivityKit
import WidgetKit
import SwiftUI

// MARK: - Live Activity Attributes

struct JARVISActivityAttributes: ActivityAttributes {
    /// Fixed context that doesn't change during the activity
    struct ContentState: Codable, Hashable {
        var status: String
        var taskDescription: String
        var progress: Double          // 0.0 - 1.0
        var elapsedSeconds: Int
    }

    /// Static data set at start
    let taskType: String              // "research", "voice_call", "processing"
    let startedAt: Date
}

// MARK: - Live Activity Widget

struct JARVISLiveActivity: Widget {
    var body: some WidgetConfiguration {
        ActivityConfiguration(for: JARVISActivityAttributes.self) { context in
            // Lock screen / banner presentation
            lockScreenView(context: context)
        } dynamicIsland: { context in
            DynamicIsland {
                // Expanded regions
                DynamicIslandExpandedRegion(.leading) {
                    HStack(spacing: 4) {
                        Circle()
                            .fill(statusColor(context.state.status))
                            .frame(width: 6, height: 6)
                        Text("JARVIS")
                            .font(.system(size: 11, weight: .bold, design: .monospaced))
                            .foregroundColor(WidgetColors.cyan)
                    }
                }

                DynamicIslandExpandedRegion(.trailing) {
                    Text(formattedDuration(context.state.elapsedSeconds))
                        .font(.system(size: 11, design: .monospaced))
                        .foregroundColor(WidgetColors.textDim)
                }

                DynamicIslandExpandedRegion(.center) {
                    Text(context.state.taskDescription)
                        .font(.system(size: 13, weight: .medium, design: .monospaced))
                        .foregroundColor(.white)
                        .lineLimit(1)
                }

                DynamicIslandExpandedRegion(.bottom) {
                    // Progress bar
                    ProgressView(value: context.state.progress)
                        .tint(WidgetColors.cyan)
                        .padding(.horizontal, 4)
                }
            } compactLeading: {
                HStack(spacing: 3) {
                    Circle()
                        .fill(statusColor(context.state.status))
                        .frame(width: 5, height: 5)
                    Image(systemName: iconForTask(context.attributes.taskType))
                        .font(.system(size: 10))
                        .foregroundColor(WidgetColors.cyan)
                }
            } compactTrailing: {
                Text(formattedDuration(context.state.elapsedSeconds))
                    .font(.system(size: 11, weight: .medium, design: .monospaced))
                    .foregroundColor(.white)
            } minimal: {
                Image(systemName: iconForTask(context.attributes.taskType))
                    .font(.system(size: 12))
                    .foregroundColor(WidgetColors.cyan)
            }
        }
    }

    // MARK: - Lock Screen View

    @ViewBuilder
    private func lockScreenView(context: ActivityViewContext<JARVISActivityAttributes>) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                HStack(spacing: 4) {
                    Circle()
                        .fill(statusColor(context.state.status))
                        .frame(width: 6, height: 6)
                    Text("JARVIS")
                        .font(.system(size: 11, weight: .bold, design: .monospaced))
                        .foregroundColor(WidgetColors.cyan)
                }

                Spacer()

                Text(formattedDuration(context.state.elapsedSeconds))
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundColor(WidgetColors.textDim)
            }

            Text(context.state.taskDescription)
                .font(.system(size: 14, weight: .medium, design: .monospaced))
                .foregroundColor(.white)
                .lineLimit(2)

            ProgressView(value: context.state.progress)
                .tint(WidgetColors.cyan)

            Text(context.state.status.uppercased())
                .font(.system(size: 9, weight: .bold, design: .monospaced))
                .foregroundColor(statusColor(context.state.status))
                .tracking(1.0)
        }
        .padding(16)
        .activityBackgroundTint(Color(red: 0.02, green: 0.02, blue: 0.06))
    }

    // MARK: - Helpers

    private func statusColor(_ status: String) -> Color {
        switch status.lowercased() {
        case "active", "running", "healthy":
            return WidgetColors.online
        case "paused", "waiting":
            return WidgetColors.warning
        case "error", "failed":
            return WidgetColors.error
        default:
            return WidgetColors.cyan
        }
    }

    private func iconForTask(_ taskType: String) -> String {
        switch taskType {
        case "research": return "magnifyingglass"
        case "voice_call": return "phone.fill"
        case "processing": return "cpu"
        case "briefing": return "doc.text"
        default: return "cpu"
        }
    }

    private func formattedDuration(_ seconds: Int) -> String {
        let minutes = seconds / 60
        let secs = seconds % 60
        if minutes > 0 {
            return "\(minutes)m \(secs)s"
        }
        return "\(secs)s"
    }
}
