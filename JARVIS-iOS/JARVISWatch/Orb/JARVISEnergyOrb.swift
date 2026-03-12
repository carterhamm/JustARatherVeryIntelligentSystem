import SwiftUI

/// JARVIS Energy Orb — continuous particle ring with Möbius-style twisting.
/// The tube cross-section rotates as it goes around the ring, so the band
/// of particles twists like a ribbon. The twist animates over time, creating
/// organic alive movement without changing the ring's circular shape.

struct JARVISEnergyOrb: View {
    let audioLevel: Float
    let isActive: Bool
    let isSpeaking: Bool

    private let cyan = Color(red: 0, green: 212.0/255, blue: 1)
    private let cyanWhite = Color(red: 0.7, green: 0.95, blue: 1.0)

    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0/60.0)) { timeline in
            let t = timeline.date.timeIntervalSinceReferenceDate
            Canvas { context, size in
                drawParticleRing(context: &context, size: size, time: t)
            }
        }
    }

    private func drawParticleRing(context: inout GraphicsContext, size: CGSize, time: Double) {
        let cx = size.width / 2
        let cy = size.height / 2
        let baseRadius = min(size.width, size.height) * 0.55
        let al = Double(audioLevel)

        // --- Ambient glow ---
        let glowR = baseRadius * 1.25
        context.fill(
            Path(ellipseIn: CGRect(x: cx - glowR, y: cy - glowR, width: glowR * 2, height: glowR * 2)),
            with: .radialGradient(
                Gradient(colors: [
                    cyan.opacity(0.07 + al * 0.05),
                    cyan.opacity(0.015),
                    .clear
                ]),
                center: CGPoint(x: cx, y: cy),
                startRadius: baseRadius * 0.6,
                endRadius: glowR
            )
        )

        // Möbius twist speed — the twist pattern rotates around the ring over time
        let twistSpeed = time * 0.4

        // Layer config: (radiusOffset, particleCount, scatterWidth, baseAlpha, baseSize)
        let layers: [(Double, Int, Double, Double, Double)] = [
            // Outer haze
            (1.07, 1200, 2.6, 0.05, 1.8),
            (1.04, 800,  2.0, 0.07, 1.5),
            // Main ring body
            (1.00, 2500, 1.0, 0.35, 1.2),
            (0.98, 2000, 0.8, 0.45, 1.0),
            (0.96, 1500, 0.6, 0.55, 0.9),
            // Inner bright edge
            (0.93, 1000, 0.4, 0.50, 0.7),
        ]

        for (rFactor, count, scatterWidth, baseAlpha, baseSize) in layers {
            let layerR = baseRadius * rFactor

            for i in 0..<count {
                let fi = Double(i)
                let angle = (fi / Double(count)) * 2 * Double.pi

                // --- Subtle radius warp (keeps ring circular but alive) ---
                let w1 = sin(angle * 2.0 + time * 0.5) * 0.012
                let w2 = sin(angle * 5.0 - time * 0.4) * 0.007
                let w3 = cos(angle * 3.0 + time * 0.3) * 0.008
                let wAudio = sin(angle * 1.5 + time * 1.2) * al * 0.02
                let r = layerR * (1 + w1 + w2 + w3 + wAudio)

                // --- Thickness (subtle variation, not dramatic) ---
                let thickness = 1.0
                    + 0.2 * sin(angle * 2 + time * 0.25)
                    + al * 0.3 * sin(angle * 1.5 + time * 0.8)

                // --- Deterministic scatter offset for this particle ---
                let hash = sin(fi * 127.1 + 311.7) * 43758.5453
                let scatter01 = hash - floor(hash)
                let scatterOffset = (scatter01 - 0.5) * 2.0  // -1..1
                let perpDist = scatterOffset * scatterWidth * thickness * 3.0

                // --- Möbius twist ---
                // The scatter direction rotates as we go around the ring.
                // Half-twist (angle * 0.5) = true Möbius, animated by twistSpeed.
                // This makes the ribbon of particles twist and roll continuously.
                let twistAngle = angle * 0.5 + twistSpeed

                // Radial direction (points away from center)
                let radX = cos(angle)
                let radY = sin(angle)
                // Tangent direction (perpendicular to radial, along the ring)
                let tanX = -sin(angle)
                let tanY = cos(angle)

                // Twisted scatter direction — blends radial and tangent
                let dirX = radX * cos(twistAngle) + tanX * sin(twistAngle)
                let dirY = radY * cos(twistAngle) + tanY * sin(twistAngle)

                // Final particle position
                let px = cx + radX * r + dirX * perpDist
                let py = cy + radY * r + dirY * perpDist

                // --- Alpha ---
                let distFromCenter = abs(scatterOffset)
                let edgeFade = 1.0 - distFromCenter * distFromCenter
                let alpha = baseAlpha * edgeFade * thickness * 0.7
                guard alpha > 0.01 else { continue }

                // --- Size ---
                let pSize = baseSize * (0.7 + thickness * 0.3) * (1 + al * 0.4)

                // --- Sparkle ---
                let sparkle = sin(fi * 2.618 + time * 3.0)
                let isSpark = sparkle > 0.88 && distFromCenter < 0.3

                let rect = CGRect(x: px - pSize/2, y: py - pSize/2, width: pSize, height: pSize)

                if isSpark {
                    let sa = alpha * 1.8
                    context.fill(Path(ellipseIn: rect), with: .color(cyanWhite.opacity(sa)))
                    let gr = pSize * 2.5
                    let gRect = CGRect(x: px - gr/2, y: py - gr/2, width: gr, height: gr)
                    context.fill(Path(ellipseIn: gRect), with: .color(cyan.opacity(sa * 0.25)))
                } else {
                    context.fill(Path(ellipseIn: rect), with: .color(cyan.opacity(alpha)))
                }
            }
        }

        // --- Wisps ---
        let wispCount = 8 + Int(al * 6)
        for i in 0..<wispCount {
            let baseAngle = Double(i) / Double(wispCount) * 2 * Double.pi
            let offset = sin(time * 0.2 + Double(i) * 0.7) * 0.3
            let start = baseAngle + offset
            let len = 0.15 + sin(time * 0.4 + Double(i) * 1.3) * 0.08 + al * 0.1

            var path = Path()
            for j in 0...15 {
                let frac = Double(j) / 15.0
                let a = start + frac * len
                let rOff = sin(frac * Double.pi * 2 + time * 0.5) * 4
                let wr = baseRadius + rOff + (1 - frac) * 3
                let pt = CGPoint(x: cx + cos(a) * wr, y: cy + sin(a) * wr)
                if j == 0 { path.move(to: pt) } else { path.addLine(to: pt) }
            }
            context.stroke(
                path,
                with: .color(cyan.opacity(0.1 + al * 0.07)),
                style: StrokeStyle(lineWidth: 1.5, lineCap: .round)
            )
        }

        // --- Inner void glow ---
        let innerR = baseRadius * 0.45 * (1 + al * 0.12)
        context.fill(
            Path(ellipseIn: CGRect(x: cx - innerR, y: cy - innerR, width: innerR * 2, height: innerR * 2)),
            with: .radialGradient(
                Gradient(colors: [cyan.opacity(0.04 + al * 0.05), .clear]),
                center: CGPoint(x: cx, y: cy),
                startRadius: 0,
                endRadius: innerR
            )
        )
    }
}

#Preview {
    ZStack {
        Color.black.ignoresSafeArea()
        JARVISEnergyOrb(audioLevel: 0.3, isActive: true, isSpeaking: false)
            .frame(width: 200, height: 200)
    }
}
