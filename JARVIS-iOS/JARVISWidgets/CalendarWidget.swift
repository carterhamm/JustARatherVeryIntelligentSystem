import WidgetKit
import SwiftUI
import EventKit

// MARK: - Widget Definition

struct JARVISCalendarWidget: Widget {
    let kind = "JARVISCalendar"

    var body: some WidgetConfiguration {
        StaticConfiguration(kind: kind, provider: CalendarProvider()) { entry in
            CalendarWidgetView(entry: entry)
        }
        .configurationDisplayName("JARVIS Schedule")
        .description("Your next events at a glance")
        .supportedFamilies([.systemSmall, .systemMedium, .accessoryRectangular])
    }
}

// MARK: - Models

struct CalendarEvent {
    let title: String
    let startDate: Date
    let endDate: Date
    let isAllDay: Bool
    let calendarColor: Color
}

struct CalendarEntry: TimelineEntry {
    let date: Date
    let events: [CalendarEvent]
    let authorized: Bool

    var nextEvent: CalendarEvent? { events.first }
    var hasEvents: Bool { !events.isEmpty }
}

// MARK: - Timeline Provider

struct CalendarProvider: TimelineProvider {
    private let store = EKEventStore()

    func placeholder(in context: Context) -> CalendarEntry {
        CalendarEntry(
            date: .now,
            events: [
                CalendarEvent(
                    title: "Project Review",
                    startDate: Date().addingTimeInterval(3600),
                    endDate: Date().addingTimeInterval(7200),
                    isAllDay: false,
                    calendarColor: WidgetColors.cyan
                ),
                CalendarEvent(
                    title: "Lunch with Spencer",
                    startDate: Date().addingTimeInterval(10800),
                    endDate: Date().addingTimeInterval(14400),
                    isAllDay: false,
                    calendarColor: WidgetColors.gold
                ),
            ],
            authorized: true
        )
    }

    func getSnapshot(in context: Context, completion: @escaping (CalendarEntry) -> Void) {
        completion(placeholder(in: context))
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<CalendarEntry>) -> Void) {
        let authStatus = EKEventStore.authorizationStatus(for: .event)

        guard authStatus == .fullAccess else {
            let entry = CalendarEntry(date: .now, events: [], authorized: false)
            let timeline = Timeline(entries: [entry], policy: .after(Date().addingTimeInterval(3600)))
            completion(timeline)
            return
        }

        let now = Date()
        let endOfDay = Calendar.current.date(bySettingHour: 23, minute: 59, second: 59, of: now) ?? now.addingTimeInterval(86400)

        let predicate = store.predicateForEvents(withStart: now, end: endOfDay, calendars: nil)
        let ekEvents = store.events(matching: predicate)
            .sorted { $0.startDate < $1.startDate }
            .prefix(4)

        let events: [CalendarEvent] = ekEvents.map { event in
            CalendarEvent(
                title: event.title ?? "Untitled",
                startDate: event.startDate,
                endDate: event.endDate,
                isAllDay: event.isAllDay,
                calendarColor: Color(cgColor: event.calendar.cgColor)
            )
        }

        let entry = CalendarEntry(date: now, events: events, authorized: true)

        // Refresh at next event start or in 30 minutes, whichever is sooner
        let nextEventDate = events.first?.startDate ?? now.addingTimeInterval(1800)
        let nextRefresh = min(nextEventDate, now.addingTimeInterval(1800))
        let timeline = Timeline(entries: [entry], policy: .after(nextRefresh))
        completion(timeline)
    }
}

// MARK: - Widget Views

struct CalendarWidgetView: View {
    let entry: CalendarEntry
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
                Image(systemName: "calendar")
                    .font(.system(size: 8))
                    .foregroundColor(WidgetColors.cyan)
                Text("SCHEDULE")
                    .font(.system(size: 8, weight: .bold, design: .monospaced))
                    .foregroundColor(WidgetColors.cyan)
                    .tracking(1.0)
            }

            Spacer()

            if !entry.authorized {
                unauthorizedView
            } else if let event = entry.nextEvent {
                nextEventSmallView(event)
            } else {
                noEventsView
            }
        }
        .padding(12)
        .containerBackground(for: .widget) {
            WidgetColors.background
        }
    }

    // MARK: Medium

    private var mediumView: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 4) {
                Image(systemName: "calendar")
                    .font(.system(size: 8))
                    .foregroundColor(WidgetColors.cyan)
                Text("SCHEDULE")
                    .font(.system(size: 8, weight: .bold, design: .monospaced))
                    .foregroundColor(WidgetColors.cyan)
                    .tracking(1.0)
                Spacer()
                Text(entry.date, style: .date)
                    .font(.system(size: 8, design: .monospaced))
                    .foregroundColor(WidgetColors.textDim.opacity(0.6))
            }

            if !entry.authorized {
                unauthorizedView
            } else if entry.hasEvents {
                ForEach(Array(entry.events.prefix(3).enumerated()), id: \.offset) { _, event in
                    eventRow(event)
                }
                if entry.events.count > 3 {
                    Text("+\(entry.events.count - 3) more")
                        .font(.system(size: 8, design: .monospaced))
                        .foregroundColor(WidgetColors.textDim)
                }
            } else {
                Spacer()
                noEventsView
                Spacer()
            }
        }
        .padding(12)
        .containerBackground(for: .widget) {
            WidgetColors.background
        }
    }

    // MARK: Lock Screen (Rectangular)

    private var rectangularView: some View {
        VStack(alignment: .leading, spacing: 2) {
            if let event = entry.nextEvent {
                HStack(spacing: 4) {
                    Image(systemName: "calendar")
                        .font(.system(size: 8))
                    Text("NEXT")
                        .font(.system(size: 8, weight: .bold, design: .monospaced))
                }
                Text(event.title)
                    .font(.system(size: 11, weight: .medium, design: .monospaced))
                    .lineLimit(1)
                Text(event.startDate, style: .time)
                    .font(.system(size: 10, design: .monospaced))
            } else {
                HStack(spacing: 4) {
                    Image(systemName: "calendar")
                        .font(.system(size: 8))
                    Text("CLEAR")
                        .font(.system(size: 10, weight: .bold, design: .monospaced))
                }
                Text("No events remaining")
                    .font(.system(size: 10, design: .monospaced))
            }
        }
    }

    // MARK: Shared Components

    private func nextEventSmallView(_ event: CalendarEvent) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text("NEXT")
                .font(.system(size: 7, weight: .bold, design: .monospaced))
                .foregroundColor(WidgetColors.cyan.opacity(0.5))
                .tracking(1.0)

            Text(event.title)
                .font(.system(size: 13, weight: .medium, design: .monospaced))
                .foregroundColor(.white)
                .lineLimit(2)

            if event.isAllDay {
                Text("ALL DAY")
                    .font(.system(size: 9, weight: .bold, design: .monospaced))
                    .foregroundColor(WidgetColors.gold)
            } else {
                Text(event.startDate, style: .time)
                    .font(.system(size: 11, weight: .bold, design: .monospaced))
                    .foregroundColor(WidgetColors.cyan)
            }

            if entry.events.count > 1 {
                Text("+\(entry.events.count - 1) more today")
                    .font(.system(size: 7, design: .monospaced))
                    .foregroundColor(WidgetColors.textDim)
            }
        }
    }

    private func eventRow(_ event: CalendarEvent) -> some View {
        HStack(spacing: 6) {
            // Calendar color indicator
            RoundedRectangle(cornerRadius: 1)
                .fill(event.calendarColor)
                .frame(width: 2, height: 20)

            VStack(alignment: .leading, spacing: 1) {
                Text(event.title)
                    .font(.system(size: 11, weight: .medium, design: .monospaced))
                    .foregroundColor(.white)
                    .lineLimit(1)

                if event.isAllDay {
                    Text("ALL DAY")
                        .font(.system(size: 8, weight: .bold, design: .monospaced))
                        .foregroundColor(WidgetColors.gold)
                } else {
                    Text("\(event.startDate, style: .time) - \(event.endDate, style: .time)")
                        .font(.system(size: 8, design: .monospaced))
                        .foregroundColor(WidgetColors.textDim)
                }
            }

            Spacer()
        }
    }

    private var noEventsView: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text("ALL CLEAR")
                .font(.system(size: 12, weight: .bold, design: .monospaced))
                .foregroundColor(WidgetColors.online)
            Text("No events remaining")
                .font(.system(size: 9, design: .monospaced))
                .foregroundColor(WidgetColors.textDim)
        }
    }

    private var unauthorizedView: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text("RESTRICTED")
                .font(.system(size: 11, weight: .bold, design: .monospaced))
                .foregroundColor(WidgetColors.warning)
            Text("Calendar access required")
                .font(.system(size: 9, design: .monospaced))
                .foregroundColor(WidgetColors.textDim)
        }
    }
}

// MARK: - Preview

#Preview("Small", as: .systemSmall) {
    JARVISCalendarWidget()
} timeline: {
    CalendarEntry(
        date: .now,
        events: [
            CalendarEvent(title: "Team Standup", startDate: Date().addingTimeInterval(1800), endDate: Date().addingTimeInterval(3600), isAllDay: false, calendarColor: .blue),
            CalendarEvent(title: "Lunch", startDate: Date().addingTimeInterval(7200), endDate: Date().addingTimeInterval(10800), isAllDay: false, calendarColor: .green),
        ],
        authorized: true
    )
}

#Preview("Medium", as: .systemMedium) {
    JARVISCalendarWidget()
} timeline: {
    CalendarEntry(
        date: .now,
        events: [
            CalendarEvent(title: "Team Standup", startDate: Date().addingTimeInterval(1800), endDate: Date().addingTimeInterval(3600), isAllDay: false, calendarColor: .blue),
            CalendarEvent(title: "Lunch with Spencer", startDate: Date().addingTimeInterval(7200), endDate: Date().addingTimeInterval(10800), isAllDay: false, calendarColor: .green),
            CalendarEvent(title: "Code Review", startDate: Date().addingTimeInterval(14400), endDate: Date().addingTimeInterval(18000), isAllDay: false, calendarColor: .purple),
        ],
        authorized: true
    )
}
