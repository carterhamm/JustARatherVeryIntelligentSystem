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

// MARK: - Angular Glass Modifiers

struct GlassBackground: ViewModifier {
    var opacity: Double = 0.45
    var cutSize: CGFloat = 10

    func body(content: Content) -> some View {
        content
            .background {
                HexCornerShape(cutSize: cutSize)
                    .fill(.ultraThinMaterial)
                    .overlay {
                        HexCornerShape(cutSize: cutSize)
                            .fill(Color.jarvisPanelBg.opacity(opacity))
                    }
                    .overlay {
                        HexCornerShape(cutSize: cutSize)
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
                HexCornerShape(cutSize: 6)
                    .fill(.ultraThinMaterial)
                    .overlay {
                        HexCornerShape(cutSize: 6)
                            .fill(Color.jarvisPanelBg.opacity(opacity))
                    }
                    .overlay {
                        HexCornerShape(cutSize: 6)
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
        cutSize: CGFloat = 10
    ) -> some View {
        modifier(GlassBackground(opacity: opacity, cutSize: cutSize))
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

    func hudAccentCorners(
        cutSize: CGFloat = 8,
        color: Color = .jarvisBlue,
        opacity: Double = 0.35,
        lineLength: CGFloat = 14
    ) -> some View {
        self.overlay {
            HUDCornerAccents(
                cutSize: cutSize, color: color,
                opacity: opacity, lineLength: lineLength
            )
        }
    }
}

// MARK: - Scanline Overlay

struct ScanlineOverlay: View {
    @State private var phase: CGFloat = 0

    var body: some View {
        Canvas { context, size in
            let spacing: CGFloat = 20
            let dotRadius: CGFloat = 1.2
            let cols = Int(size.width / spacing) + 1
            let rows = Int(size.height / spacing) + 1

            for row in 0..<rows {
                for col in 0..<cols {
                    let x = CGFloat(col) * spacing
                    let y = CGFloat(row) * spacing

                    // Wave from top-left to bottom-right
                    let diagonal = (x + y) / (size.width + size.height)
                    let wave = sin((diagonal * 4 - phase) * .pi * 2)
                    let opacity = 0.03 + 0.06 * max(0, wave)

                    context.fill(
                        Path(ellipseIn: CGRect(x: x - dotRadius, y: y - dotRadius, width: dotRadius * 2, height: dotRadius * 2)),
                        with: .color(.white.opacity(opacity))
                    )
                }
            }
        }
        .onAppear {
            withAnimation(.linear(duration: 6).repeatForever(autoreverses: false)) {
                phase = 1
            }
        }
        .allowsHitTesting(false)
    }
}

// MARK: - Hex Corner Clip (Angular Shape)

struct HexCornerShape: InsettableShape {
    var cutSize: CGFloat = 8
    var insetAmount: CGFloat = 0

    func path(in rect: CGRect) -> Path {
        let r = rect.insetBy(dx: insetAmount, dy: insetAmount)
        let c = max(0, cutSize - insetAmount)
        return Path { p in
            p.move(to: CGPoint(x: r.minX + c, y: r.minY))
            p.addLine(to: CGPoint(x: r.maxX - c, y: r.minY))
            p.addLine(to: CGPoint(x: r.maxX, y: r.minY + c))
            p.addLine(to: CGPoint(x: r.maxX, y: r.maxY - c))
            p.addLine(to: CGPoint(x: r.maxX - c, y: r.maxY))
            p.addLine(to: CGPoint(x: r.minX + c, y: r.maxY))
            p.addLine(to: CGPoint(x: r.minX, y: r.maxY - c))
            p.addLine(to: CGPoint(x: r.minX, y: r.minY + c))
            p.closeSubpath()
        }
    }

    func inset(by amount: CGFloat) -> HexCornerShape {
        var shape = self
        shape.insetAmount += amount
        return shape
    }
}

// MARK: - HUD Corner Accent Overlay

struct HUDCornerAccents: View {
    var cutSize: CGFloat = 8
    var color: Color = .jarvisBlue
    var opacity: Double = 0.35
    var lineLength: CGFloat = 14

    var body: some View {
        Canvas { ctx, size in
            let w = size.width
            let h = size.height
            let c = cutSize

            // Top-left
            var tl = Path()
            tl.move(to: CGPoint(x: 0, y: c + lineLength))
            tl.addLine(to: CGPoint(x: 0, y: c))
            tl.addLine(to: CGPoint(x: c, y: 0))
            tl.addLine(to: CGPoint(x: c + lineLength, y: 0))
            ctx.stroke(tl, with: .color(color.opacity(opacity)), lineWidth: 1)

            // Top-right
            var tr = Path()
            tr.move(to: CGPoint(x: w - c - lineLength, y: 0))
            tr.addLine(to: CGPoint(x: w - c, y: 0))
            tr.addLine(to: CGPoint(x: w, y: c))
            tr.addLine(to: CGPoint(x: w, y: c + lineLength))
            ctx.stroke(tr, with: .color(color.opacity(opacity)), lineWidth: 1)

            // Bottom-right
            var br = Path()
            br.move(to: CGPoint(x: w, y: h - c - lineLength))
            br.addLine(to: CGPoint(x: w, y: h - c))
            br.addLine(to: CGPoint(x: w - c, y: h))
            br.addLine(to: CGPoint(x: w - c - lineLength, y: h))
            ctx.stroke(br, with: .color(color.opacity(opacity)), lineWidth: 1)

            // Bottom-left
            var bl = Path()
            bl.move(to: CGPoint(x: c + lineLength, y: h))
            bl.addLine(to: CGPoint(x: c, y: h))
            bl.addLine(to: CGPoint(x: 0, y: h - c))
            bl.addLine(to: CGPoint(x: 0, y: h - c - lineLength))
            ctx.stroke(bl, with: .color(color.opacity(opacity)), lineWidth: 1)
        }
        .allowsHitTesting(false)
    }
}

// MARK: - Vignette Overlay

struct VignetteOverlay: View {
    var body: some View {
        RadialGradient(
            colors: [
                .clear,
                .clear,
                Color.black.opacity(0.3),
                Color.black.opacity(0.7)
            ],
            center: .center,
            startRadius: 100,
            endRadius: UIScreen.main.bounds.height * 0.7
        )
        .ignoresSafeArea()
        .allowsHitTesting(false)
    }
}

// MARK: - HUD Frame Corners

struct HUDCorner: View {
    let position: CornerPosition
    enum CornerPosition { case topLeft, topRight, bottomLeft, bottomRight }

    var body: some View {
        Canvas { context, size in
            let len: CGFloat = 24
            let color = Color.jarvisBlue.opacity(0.12)

            var path = Path()
            switch position {
            case .topLeft:
                path.move(to: CGPoint(x: 0, y: len))
                path.addLine(to: .zero)
                path.addLine(to: CGPoint(x: len, y: 0))
            case .topRight:
                path.move(to: CGPoint(x: size.width - len, y: 0))
                path.addLine(to: CGPoint(x: size.width, y: 0))
                path.addLine(to: CGPoint(x: size.width, y: len))
            case .bottomLeft:
                path.move(to: CGPoint(x: 0, y: size.height - len))
                path.addLine(to: CGPoint(x: 0, y: size.height))
                path.addLine(to: CGPoint(x: len, y: size.height))
            case .bottomRight:
                path.move(to: CGPoint(x: size.width, y: size.height - len))
                path.addLine(to: CGPoint(x: size.width, y: size.height))
                path.addLine(to: CGPoint(x: size.width - len, y: size.height))
            }
            context.stroke(path, with: .color(color), lineWidth: 1)
        }
        .frame(width: 36, height: 36)
        .allowsHitTesting(false)
    }
}

// MARK: - HUD Edge Lines

struct HUDEdgeLines: View {
    var body: some View {
        GeometryReader { geo in
            // Top
            Rectangle()
                .fill(
                    LinearGradient(
                        colors: [.clear, Color.jarvisBlue.opacity(0.08), .clear],
                        startPoint: .leading,
                        endPoint: .trailing
                    )
                )
                .frame(height: 0.5)
                .offset(y: 0)
                .padding(.horizontal, 44)

            // Bottom
            Rectangle()
                .fill(
                    LinearGradient(
                        colors: [.clear, Color.jarvisBlue.opacity(0.06), .clear],
                        startPoint: .leading,
                        endPoint: .trailing
                    )
                )
                .frame(height: 0.5)
                .offset(y: geo.size.height - 0.5)
                .padding(.horizontal, 44)

            // Left
            Rectangle()
                .fill(
                    LinearGradient(
                        colors: [.clear, Color.jarvisBlue.opacity(0.06), .clear],
                        startPoint: .top,
                        endPoint: .bottom
                    )
                )
                .frame(width: 0.5)
                .offset(x: 0)
                .padding(.vertical, 44)

            // Right
            Rectangle()
                .fill(
                    LinearGradient(
                        colors: [.clear, Color.jarvisBlue.opacity(0.06), .clear],
                        startPoint: .top,
                        endPoint: .bottom
                    )
                )
                .frame(width: 0.5)
                .offset(x: geo.size.width - 0.5)
                .padding(.vertical, 44)
        }
        .allowsHitTesting(false)
    }
}
