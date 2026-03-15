# JARVISWidgets — Xcode Setup

Widget extensions require a separate target. These steps cannot be automated via CLI.

## 1. Add Widget Extension Target

1. Open `JARVIS.xcodeproj` in Xcode
2. File > New > Target > Widget Extension
3. Product Name: `JARVISWidgets`
4. Team: HKM8P29B68
5. Bundle Identifier: `dev.jarvis.malibupoint.widgets`
6. **Uncheck** "Include Configuration App Intent"
7. **Uncheck** "Include Live Activity" (we provide our own)
8. Click Finish

## 2. Replace Generated Files

Xcode generates placeholder files. Delete them and use the files in this directory:

- `JARVISWidgets.swift` — Widget bundle entry point (@main)
- `StatusWidget.swift` — JARVIS health status widget
- `CalendarWidget.swift` — Upcoming calendar events widget
- `LiveActivity.swift` — Live Activity for ongoing tasks (Dynamic Island + Lock Screen)
- `WidgetColors.swift` — Color palette matching JARVISTheme (standalone for extension)
- `Info.plist` — Extension metadata

## 3. Configure Target

1. Select the `JARVISWidgets` target in project settings
2. General > Deployment Info: iOS 17.0
3. Signing: Team HKM8P29B68, auto-manage signing
4. Build Settings > verify `INFOPLIST_FILE` points to `JARVISWidgets/Info.plist`

## 4. App Group (for shared data)

If you want widgets to share data with the main app (e.g. auth tokens, cached data):

1. Select the **JARVIS** (main app) target > Signing & Capabilities
2. Add Capability > App Groups
3. Create group: `group.dev.jarvis.malibupoint`
4. Select the **JARVISWidgets** target > Signing & Capabilities
5. Add Capability > App Groups
6. Select the same group: `group.dev.jarvis.malibupoint`
7. Use `UserDefaults(suiteName: "group.dev.jarvis.malibupoint")` for shared storage

## 5. Live Activity Entitlement

1. Select the **JARVIS** (main app) target
2. Add Capability > "Supports Live Activities" (in Info.plist: `NSSupportsLiveActivities = YES`)
3. The widget extension already includes ActivityKit support

## 6. EventKit for Calendar Widget

The calendar widget reads from EventKit directly:

1. Select the **JARVISWidgets** target
2. No additional entitlements needed — EventKit access follows the main app's permission grant
3. The main app must have already requested calendar access for the widget to show events

## 7. Build and Test

```bash
xcodebuild -project JARVIS-iOS/JARVIS.xcodeproj -scheme JARVIS \
  -destination 'generic/platform=iOS' build
```

Test widgets in Xcode via: Product > Scheme > JARVISWidgets > Run (select widget preview)

## Files Overview

| File | Purpose |
|------|---------|
| `JARVISWidgets.swift` | @main WidgetBundle — registers all widgets |
| `StatusWidget.swift` | Shows JARVIS health status (small/medium/lock screen) |
| `CalendarWidget.swift` | Shows upcoming calendar events (small/medium/lock screen) |
| `LiveActivity.swift` | Dynamic Island + Lock Screen for ongoing JARVIS tasks |
| `WidgetColors.swift` | Color palette matching the MCU HUD aesthetic |
| `Info.plist` | WidgetKit extension point identifier |
