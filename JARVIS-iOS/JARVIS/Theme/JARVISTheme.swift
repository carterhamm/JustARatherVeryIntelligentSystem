import SwiftUI

// MARK: - JARVIS Color Palette

extension Color {
    // Primary
    static let jarvisBlue = Color(hex: "00d4ff")
    static let jarvisCyan = Color(hex: "00f0ff")
    static let jarvisGold = Color(hex: "f0a500")

    // Backgrounds
    static let jarvisDark = Color(hex: "0a0a1a")
    static let jarvisDeepDark = Color(hex: "050510")
    static let jarvisPanelBg = Color(hex: "080c18")

    // Status
    static let jarvisOnline = Color(hex: "39ff14")
    static let jarvisError = Color(hex: "ff3a3a")
    static let jarvisWarning = Color(hex: "ffbf00")

    // Text
    static let jarvisText = Color(hex: "e0e8f0")
    static let jarvisTextDim = Color(hex: "8090a0")

    // Glass
    static let jarvisGlassBorder = Color.white.opacity(0.06)
    static let jarvisGlassFill = Color(hex: "080c18").opacity(0.45)

    init(hex: String) {
        let hex = hex.trimmingCharacters(in: .alphanumerics.inverted)
        var int: UInt64 = 0
        Scanner(string: hex).scanHexInt64(&int)
        let a, r, g, b: UInt64
        switch hex.count {
        case 6:
            (a, r, g, b) = (255, (int >> 16) & 0xFF, (int >> 8) & 0xFF, int & 0xFF)
        case 8:
            (a, r, g, b) = ((int >> 24) & 0xFF, (int >> 16) & 0xFF, (int >> 8) & 0xFF, int & 0xFF)
        default:
            (a, r, g, b) = (255, 0, 212, 255)
        }
        self.init(
            .sRGB,
            red: Double(r) / 255,
            green: Double(g) / 255,
            blue: Double(b) / 255,
            opacity: Double(a) / 255
        )
    }
}

// MARK: - Glass Morphism Modifiers

struct GlassBackground: ViewModifier {
    var opacity: Double = 0.45
    var blurRadius: CGFloat = 24
    var cornerRadius: CGFloat = 16

    func body(content: Content) -> some View {
        content
            .background {
                RoundedRectangle(cornerRadius: cornerRadius)
                    .fill(.ultraThinMaterial)
                    .overlay {
                        RoundedRectangle(cornerRadius: cornerRadius)
                            .fill(Color.jarvisPanelBg.opacity(opacity))
                    }
                    .overlay {
                        RoundedRectangle(cornerRadius: cornerRadius)
                            .strokeBorder(Color.jarvisGlassBorder, lineWidth: 0.5)
                    }
            }
    }
}

struct GlassCapsule: ViewModifier {
    var opacity: Double = 0.5

    func body(content: Content) -> some View {
        content
            .background {
                Capsule()
                    .fill(.ultraThinMaterial)
                    .overlay {
                        Capsule()
                            .fill(Color.jarvisPanelBg.opacity(opacity))
                    }
                    .overlay {
                        Capsule()
                            .strokeBorder(Color.jarvisGlassBorder, lineWidth: 0.5)
                    }
            }
    }
}

struct CyanGlow: ViewModifier {
    var radius: CGFloat = 8
    var opacity: Double = 0.3

    func body(content: Content) -> some View {
        content
            .shadow(color: Color.jarvisBlue.opacity(opacity), radius: radius)
    }
}

extension View {
    func glassBackground(
        opacity: Double = 0.45,
        blur: CGFloat = 24,
        cornerRadius: CGFloat = 16
    ) -> some View {
        modifier(GlassBackground(opacity: opacity, blurRadius: blur, cornerRadius: cornerRadius))
    }

    func glassCapsule(opacity: Double = 0.5) -> some View {
        modifier(GlassCapsule(opacity: opacity))
    }

    func cyanGlow(radius: CGFloat = 8, opacity: Double = 0.3) -> some View {
        modifier(CyanGlow(radius: radius, opacity: opacity))
    }

    func jarvisFont(_ size: CGFloat, weight: Font.Weight = .regular) -> some View {
        self.font(.system(size: size, weight: weight, design: .monospaced))
    }

    func hudLabel() -> some View {
        self
            .font(.system(size: 9, weight: .medium, design: .monospaced))
            .textCase(.uppercase)
            .tracking(1.5)
            .foregroundColor(.jarvisBlue.opacity(0.7))
    }
}

// MARK: - Scanline Overlay

struct ScanlineOverlay: View {
    @State private var offset: CGFloat = -1

    var body: some View {
        GeometryReader { geo in
            Rectangle()
                .fill(
                    LinearGradient(
                        colors: [
                            .clear,
                            Color.jarvisBlue.opacity(0.03),
                            Color.jarvisBlue.opacity(0.06),
                            Color.jarvisBlue.opacity(0.03),
                            .clear
                        ],
                        startPoint: .top,
                        endPoint: .bottom
                    )
                )
                .frame(height: 100)
                .offset(y: offset * geo.size.height)
                .onAppear {
                    withAnimation(.linear(duration: 8).repeatForever(autoreverses: false)) {
                        offset = 1
                    }
                }
        }
        .allowsHitTesting(false)
    }
}

// MARK: - Hex Corner Clip

struct HexCornerShape: Shape {
    var cutSize: CGFloat = 8

    func path(in rect: CGRect) -> Path {
        Path { p in
            p.move(to: CGPoint(x: rect.minX + cutSize, y: rect.minY))
            p.addLine(to: CGPoint(x: rect.maxX - cutSize, y: rect.minY))
            p.addLine(to: CGPoint(x: rect.maxX, y: rect.minY + cutSize))
            p.addLine(to: CGPoint(x: rect.maxX, y: rect.maxY - cutSize))
            p.addLine(to: CGPoint(x: rect.maxX - cutSize, y: rect.maxY))
            p.addLine(to: CGPoint(x: rect.minX + cutSize, y: rect.maxY))
            p.addLine(to: CGPoint(x: rect.minX, y: rect.maxY - cutSize))
            p.addLine(to: CGPoint(x: rect.minX, y: rect.minY + cutSize))
            p.closeSubpath()
        }
    }
}
