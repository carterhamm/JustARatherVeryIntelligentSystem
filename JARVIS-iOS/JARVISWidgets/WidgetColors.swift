import SwiftUI

/// Shared color palette for all JARVIS widgets.
/// Mirrors JARVISTheme.swift but standalone (widget extensions
/// cannot link the main app target).
enum WidgetColors {
    // Primary
    static let cyan = Color(red: 0, green: 0.831, blue: 1.0)           // #00d4ff
    static let blue = Color(red: 0, green: 0.941, blue: 1.0)           // #00f0ff
    static let gold = Color(red: 0.941, green: 0.647, blue: 0)         // #f0a500

    // Backgrounds
    static let background = Color(red: 0.02, green: 0.02, blue: 0.1)   // ~#050519
    static let panelBg = Color(red: 0.031, green: 0.047, blue: 0.094)  // #080c18

    // Status
    static let online = Color(red: 0.224, green: 1.0, blue: 0.078)     // #39ff14
    static let error = Color(red: 1.0, green: 0.227, blue: 0.227)      // #ff3a3a
    static let warning = Color(red: 1.0, green: 0.749, blue: 0)        // #ffbf00

    // Text
    static let text = Color(red: 0.878, green: 0.910, blue: 0.941)     // #e0e8f0
    static let textDim = Color(red: 0.502, green: 0.565, blue: 0.627)  // #8090a0
}
