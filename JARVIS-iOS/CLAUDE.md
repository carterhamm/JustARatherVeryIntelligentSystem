# iOS/Watch App — SwiftUI

## Quick Reference
- Project: `JARVIS.xcodeproj`, Scheme: `JARVIS`
- Team ID: HKM8P29B68, Bundle: `dev.jarvis.malibupoint`
- Build check: `xcodebuild -project JARVIS.xcodeproj -scheme JARVIS -destination 'generic/platform=iOS' build`

## Design — CRITICAL
- **HexCornerShape** everywhere — NEVER use RoundedRectangle, Capsule, or Circle for UI elements
- HexCornerShape is an InsettableShape with `cutSize` parameter (4-12 typical)
- `.glassBackground(opacity:cutSize:)` modifier for glass panels
- `.hudAccentCorners(cutSize:opacity:lineLength:)` for corner accent decorations
- Colors: `.jarvisBlue`, `.jarvisGold`, `.jarvisDeepDark`, `.jarvisTextDim`, `.jarvisError`
- Fonts: `.system(design: .monospaced)` for labels and data
- ScanlineOverlay for HUD texture

## Key Files
- `Theme/JARVISTheme.swift` — HexCornerShape, colors, GlassBackground, HUDCornerAccents
- `Views/Chat/` — ChatView, MessageBubbleView, ChatInputBar
- `Views/Auth/` — LoginView, TOTPVerifyView
- `Views/Voice/VoiceModeView.swift` — Voice mode with particle visualization
- `Views/Settings/SettingsView.swift` — Settings + service connections
- `Shared/JARVISConfig.swift` — API endpoints and constants

## Auth
- Passkeys (ASAuthorizationController) + TOTP fallback
- JWT in Keychain
- SSE streaming for chat (EventSource pattern)
