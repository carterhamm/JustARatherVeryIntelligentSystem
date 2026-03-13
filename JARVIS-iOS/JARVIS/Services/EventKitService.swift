import EventKit
import os

@MainActor
class EventKitService: ObservableObject {
    static let shared = EventKitService()

    // MARK: - Published State

    @Published var reminderAuthStatus: EKAuthorizationStatus = .notDetermined
    @Published var calendarAuthStatus: EKAuthorizationStatus = .notDetermined

    // MARK: - Private

    private let store = EKEventStore()
    private let logger = Logger(subsystem: "dev.jarvis.malibupoint", category: "EventKit")

    // MARK: - Init

    init() {
        refreshAuthorizationStatus()
    }

    // MARK: - Authorization

    /// Refresh the current authorization status for both reminders and calendar.
    func refreshAuthorizationStatus() {
        reminderAuthStatus = EKEventStore.authorizationStatus(for: .reminder)
        calendarAuthStatus = EKEventStore.authorizationStatus(for: .event)
    }

    /// Request full access to both reminders and calendar (iOS 17+).
    func requestAccess() async {
        await requestReminderAccess()
        await requestCalendarAccess()
    }

    /// Request full access to reminders.
    func requestReminderAccess() async {
        do {
            let granted = try await store.requestFullAccessToReminders()
            reminderAuthStatus = EKEventStore.authorizationStatus(for: .reminder)
            logger.info("Reminders access \(granted ? "granted" : "denied")")
        } catch {
            logger.error("Reminders access request failed: \(error.localizedDescription)")
            reminderAuthStatus = EKEventStore.authorizationStatus(for: .reminder)
        }
    }

    /// Request full access to calendar events.
    func requestCalendarAccess() async {
        do {
            let granted = try await store.requestFullAccessToEvents()
            calendarAuthStatus = EKEventStore.authorizationStatus(for: .event)
            logger.info("Calendar access \(granted ? "granted" : "denied")")
        } catch {
            logger.error("Calendar access request failed: \(error.localizedDescription)")
            calendarAuthStatus = EKEventStore.authorizationStatus(for: .event)
        }
    }

    // MARK: - Reminders

    /// Fetch reminders, optionally filtering by completion status.
    func fetchReminders(completed: Bool? = nil) async -> [EKReminder] {
        guard reminderAuthStatus == .fullAccess else {
            logger.warning("Reminders not authorized")
            return []
        }

        let predicate = store.predicateForReminders(in: nil)

        return await withCheckedContinuation { continuation in
            store.fetchReminders(matching: predicate) { reminders in
                guard let reminders else {
                    continuation.resume(returning: [])
                    return
                }

                if let completed {
                    continuation.resume(returning: reminders.filter { $0.isCompleted == completed })
                } else {
                    continuation.resume(returning: reminders)
                }
            }
        }
    }

    /// Create a new reminder.
    func createReminder(title: String, notes: String? = nil, dueDate: Date? = nil, list: String? = nil) -> Bool {
        guard reminderAuthStatus == .fullAccess else {
            logger.warning("Reminders not authorized — cannot create")
            return false
        }

        let reminder = EKReminder(eventStore: store)
        reminder.title = title
        reminder.notes = notes

        if let dueDate {
            let components = Calendar.current.dateComponents(
                [.year, .month, .day, .hour, .minute],
                from: dueDate
            )
            reminder.dueDateComponents = components
        }

        // Find the target list or fall back to default
        if let listName = list {
            let calendars = store.calendars(for: .reminder)
            if let target = calendars.first(where: { $0.title.lowercased() == listName.lowercased() }) {
                reminder.calendar = target
            } else {
                reminder.calendar = store.defaultCalendarForNewReminders()
                logger.warning("List '\(listName)' not found — using default")
            }
        } else {
            reminder.calendar = store.defaultCalendarForNewReminders()
        }

        do {
            try store.save(reminder, commit: true)
            logger.info("Created reminder: \(title)")
            return true
        } catch {
            logger.error("Failed to create reminder: \(error.localizedDescription)")
            return false
        }
    }

    /// Mark a reminder as complete by its calendar item identifier.
    func completeReminder(id: String) -> Bool {
        guard reminderAuthStatus == .fullAccess else {
            logger.warning("Reminders not authorized — cannot complete")
            return false
        }

        guard let item = store.calendarItem(withIdentifier: id) as? EKReminder else {
            logger.error("Reminder not found: \(id)")
            return false
        }

        item.isCompleted = true
        item.completionDate = Date()

        do {
            try store.save(item, commit: true)
            logger.info("Completed reminder: \(item.title ?? id)")
            return true
        } catch {
            logger.error("Failed to complete reminder: \(error.localizedDescription)")
            return false
        }
    }

    // MARK: - Calendar Events

    /// Fetch calendar events between two dates.
    func fetchEvents(from startDate: Date, to endDate: Date) -> [EKEvent] {
        guard calendarAuthStatus == .fullAccess else {
            logger.warning("Calendar not authorized")
            return []
        }

        let predicate = store.predicateForEvents(withStart: startDate, end: endDate, calendars: nil)
        let events = store.events(matching: predicate)

        logger.info("Fetched \(events.count) events from \(startDate) to \(endDate)")
        return events
    }

    /// Create a new calendar event.
    func createEvent(title: String, startDate: Date, endDate: Date, notes: String? = nil) -> Bool {
        guard calendarAuthStatus == .fullAccess else {
            logger.warning("Calendar not authorized — cannot create event")
            return false
        }

        let event = EKEvent(eventStore: store)
        event.title = title
        event.startDate = startDate
        event.endDate = endDate
        event.notes = notes
        event.calendar = store.defaultCalendarForNewEvents

        do {
            try store.save(event, span: .thisEvent)
            logger.info("Created event: \(title)")
            return true
        } catch {
            logger.error("Failed to create event: \(error.localizedDescription)")
            return false
        }
    }

    // MARK: - Reminder Lists

    /// Get all available reminder lists (calendars).
    func getReminderLists() -> [EKCalendar] {
        guard reminderAuthStatus == .fullAccess else {
            logger.warning("Reminders not authorized — cannot fetch lists")
            return []
        }

        return store.calendars(for: .reminder)
    }

    // MARK: - Helpers

    /// Human-readable string for an authorization status.
    static func statusText(for status: EKAuthorizationStatus) -> String {
        switch status {
        case .notDetermined: return "Not Determined"
        case .restricted: return "Restricted"
        case .denied: return "Denied"
        case .fullAccess: return "Authorized"
        case .writeOnly: return "Write Only"
        @unknown default: return "Unknown"
        }
    }

    /// Whether the given status is considered authorized (full access).
    static func isAuthorized(_ status: EKAuthorizationStatus) -> Bool {
        status == .fullAccess
    }
}
