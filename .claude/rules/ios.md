---
paths: "JARVIS-iOS/**"
description: SwiftUI/iOS/watchOS conventions for JARVIS app
---

# iOS/Watch Rules (SwiftUI)

## Stack
- SwiftUI, iOS 17+, watchOS 10+
- Xcode project at `JARVIS-iOS/JARVIS.xcodeproj`
- Scheme: `JARVIS`

## Design System
- **HexCornerShape** (InsettableShape) — angular/chamfered corners, NEVER RoundedRectangle
- **HUDCornerAccents** — Canvas-based accent lines at corners
- **GlassBackground** — uses HexCornerShape, not rounded rects
- Colors: `.jarvisBlue`, `.jarvisGold`, `.jarvisDeepDark`, `.jarvisError`, `.jarvisTextDim`
- ScanlineOverlay for HUD effect
- Font: `.system(design: .monospaced)` for data/labels

## Auth
- Passkeys (WebAuthn via ASAuthorizationController)
- TOTP 2FA
- JWT stored in Keychain
- SSE streaming for chat (not WebSocket)
- Apple Team ID: HKM8P29B68, Bundle ID: dev.jarvis.malibupoint

## Build Verification
```bash
xcodebuild -project JARVIS-iOS/JARVIS.xcodeproj -scheme JARVIS \
  -destination 'generic/platform=iOS' build
```
Must show `** BUILD SUCCEEDED **` before committing.

## Key Files
- `Theme/JARVISTheme.swift` — colors, shapes, glass backgrounds
- `Views/Chat/` — chat interface, message bubbles, input bar
- `Views/Auth/` — login, TOTP verify
- `Services/` — API client, auth, future HealthKit/location
- `Shared/` — config, shared models
