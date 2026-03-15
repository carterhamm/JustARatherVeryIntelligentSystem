//
//  ParticleCloudView.swift
//  JARVIS
//
//  Ported from Desktop J.A.R.V.I.S. UI → iOS
//  Original: ComplexObjectBuilder.swift by Carter Hammond
//  Recolored: orange → JARVIS blue/cyan palette
//

import SwiftUI
import SceneKit

// MARK: - SwiftUI Wrapper

struct ParticleCloudView: UIViewRepresentable {
    var allowsCameraControl: Bool = true

    func makeUIView(context: Context) -> SCNView {
        let scnView = SCNView()
        scnView.scene = ParticleCloudBuilder.buildScene()
        scnView.backgroundColor = .clear
        scnView.allowsCameraControl = allowsCameraControl
        scnView.antialiasingMode = .multisampling2X
        scnView.preferredFramesPerSecond = 60
        scnView.isPlaying = true
        return scnView
    }

    func updateUIView(_ uiView: SCNView, context: Context) {}
}

// MARK: - Particle Cloud Builder

struct ParticleCloudBuilder {

    // MARK: - Color Palette (JARVIS blue/cyan)

    private static let lighterCyan = UIColor(red: 0.200, green: 0.900, blue: 1.000, alpha: 1.0)
    private static let averageCyan = UIColor(red: 0.000, green: 0.700, blue: 0.900, alpha: 1.0)
    private static let darkerCyan  = UIColor(red: 0.000, green: 0.450, blue: 0.650, alpha: 1.0)

    private struct RoadSegment {
        let tStart: Float, tEnd: Float
        let rStart: Float, rEnd: Float
        let yStart: Float, yEnd: Float
        let thickness: Float
    }

    private struct DenseZone {
        let center: Float
        let sigma: Float
        let peakDensity: Float
        let segments: [RoadSegment]
    }

    // MARK: - Nanotech Build Shader

    private static let nanotechShader = """
    #pragma body
    float3 p = _surface.position;
    float seed = fract(sin(dot(float2(p.x, p.z), float2(12.9898, 78.233))) * 43758.5453);
    float angle = atan2(p.z, p.x) / 6.28318 + 0.5;
    float r = length(float2(p.x, p.z));
    float wobble = sin(r * 18.0 + seed * 4.0) * 0.025;
    float f1 = fract(scn_frame.time * 0.007);
    float f2 = fract(scn_frame.time * 0.012 + 0.37);
    float f3 = fract(scn_frame.time * 0.004 + 0.71);
    float d1 = fract(angle - f1 + wobble + 1.0);
    float d2 = fract(angle - f2 - wobble + 1.0);
    float d3 = fract(angle - f3 + wobble * 0.5 + 1.0);
    float v1 = smoothstep(0.35, 0.01, d1);
    float v2 = smoothstep(0.28, 0.01, d2);
    float v3 = smoothstep(0.22, 0.01, d3);
    float vis = max(max(v1, v2), v3);
    vis *= 0.55 + 0.45 * seed;
    vis = max(vis, 0.05);
    _output.color.rgb *= vis;
    """

    // MARK: - Strut Build Shader

    private static let strutBuildShader = """
    #pragma body
    float3 p = _surface.position;
    float seed = fract(sin(dot(float2(p.x, p.z), float2(12.9898, 78.233))) * 43758.5453);
    float seed2 = fract(sin(dot(float2(p.y, p.x), float2(45.164, 93.233))) * 27183.8);
    float t = scn_frame.time;
    float period = 32.0;
    float groupId = floor(seed * 6.0);
    float groupPhase = fract(sin(groupId * 127.1) * 43758.5453) * 0.4;
    float delay = groupPhase * period + seed2 * 2.0;
    float effectiveT = t - delay;
    float particleOrder = fract(seed * 0.6 + seed2 * 0.4);
    float noise = sin(seed * 12.0 + t * 0.3) * 0.02;
    float vis = 0.0;
    if (effectiveT > 0.0) {
        float cyc = fract(effectiveT / period);
        if (cyc < 0.10) {
            float prog = cyc / 0.10;
            vis = smoothstep(particleOrder - 0.06, particleOrder + 0.06, prog + noise);
            float ahead = particleOrder - prog;
            if (ahead > 0.0 && ahead < 0.15) {
                vis = max(vis, (1.0 - ahead / 0.15) * seed * 0.3);
            }
        } else if (cyc < 0.78) {
            vis = 0.95 + sin(seed * 8.0 + t * 0.4) * 0.05;
        } else if (cyc < 0.90) {
            float df = (cyc - 0.78) / 0.12;
            float dissolveOrder = 1.0 - particleOrder;
            vis = 1.0 - smoothstep(dissolveOrder - 0.06, dissolveOrder + 0.06, df + noise);
            vis = max(vis, (1.0 - smoothstep(0.0, 0.08, df - dissolveOrder)) * seed2 * 0.2);
        }
    }
    vis *= 0.55 + 0.45 * seed;
    _output.color.rgb *= vis;
    """

    private static let triBridgeShader = """
    #pragma body
    float3 p = _surface.position;
    float seed = fract(sin(dot(float2(p.x, p.z), float2(12.9898, 78.233))) * 43758.5453);
    float seed2 = fract(sin(dot(float2(p.y, p.x), float2(45.164, 93.233))) * 27183.8);
    float t = scn_frame.time;
    float delay = seed * 4.0 + seed2 * 3.0;
    float effectiveT = t - delay;
    float vis = 0.0;
    if (effectiveT > 0.0) {
        float buildDur = 3.0 + seed * 2.0;
        float prog = clamp(effectiveT / buildDur, 0.0, 1.0);
        float particleOrder = fract(seed * 0.6 + seed2 * 0.4);
        vis = smoothstep(particleOrder - 0.06, particleOrder + 0.06, prog);
    }
    vis *= 0.55 + 0.45 * seed;
    _output.color.rgb *= vis;
    """

    // MARK: - Scene Assembly

    static func buildScene() -> SCNScene {
        let scene = SCNScene()
        scene.background.contents = UIColor.clear
        let root = scene.rootNode

        addNucleus(to: root)
        addDust(to: root)
        addRings(to: root)
        addCamera(to: root)

        return scene
    }

    // MARK: - Nucleus

    private static func addNucleus(to root: SCNNode) {
        var vertices: [SCNVector3] = []
        let shellR: Float = 0.35
        let shellSkin: Float = 0.025

        for _ in 0..<1800 {
            let theta = Float.random(in: 0...Float.pi * 2)
            let phi = acos(Float.random(in: -1...1))
            let r = shellR + Float.random(in: -shellSkin...shellSkin)
            vertices.append(SCNVector3(
                r * sin(phi) * cos(theta),
                r * sin(phi) * sin(theta),
                r * cos(phi)
            ))
        }

        let node = SCNNode(geometry: makePointGeometry(
            vertices: vertices, color: darkerCyan, emissionIntensity: 0.03,
            pointSize: 0.004, minScreenSize: 0.5, maxScreenSize: 1.5
        ))
        node.runAction(.repeatForever(.rotateBy(x: 0.1, y: .pi * 2, z: 0.05, duration: 35)))
        root.addChildNode(node)
    }

    // MARK: - Dust

    private static func addDust(to root: SCNNode) {
        let maxR: Float = 1.2
        var vertices: [SCNVector3] = []

        for _ in 0..<6000 {
            let u = Float.random(in: 0...1)
            let r = pow(u, 2.0) * maxR
            let theta = Float.random(in: 0...Float.pi * 2)
            let phi = acos(Float.random(in: -1...1))
            vertices.append(SCNVector3(
                r * sin(phi) * cos(theta),
                r * sin(phi) * sin(theta),
                r * cos(phi)
            ))
        }

        let node = SCNNode(geometry: makePointGeometry(
            vertices: vertices, color: darkerCyan, emissionIntensity: 0.015,
            pointSize: 0.003, minScreenSize: 0.3, maxScreenSize: 0.8
        ))
        node.runAction(.repeatForever(.rotateBy(x: 0.03, y: .pi * 2, z: 0, duration: 70)))
        root.addChildNode(node)
    }

    // MARK: - Rings

    private static func addRings(to root: SCNNode) {
        addORing(to: root)

        addCRing(to: root, major: 2.4, minor: 0.07, start: 0.5, len: .pi * 1.70,
                 tilt: (0.3, -0.2, -0.1), color: darkerCyan,
                 count: 3000, speed: 44, strutCount: 6, strutLen: 0.3...0.7,
                 spinDir: -1.0, triBridgeCount: 5)

        addCRing(to: root, major: 2.1, minor: 0.065, start: 2.8, len: .pi * 1.44,
                 tilt: (0.65, 1.4, 0.15), color: darkerCyan,
                 count: 2500, speed: 36, strutCount: 5, strutLen: 0.3...0.6,
                 triBridgeCount: 4)

        addCRing(to: root, major: 2.6, minor: 0.06, start: 1.0, len: .pi * 1.0,
                 tilt: (1.2, 0.5, -0.1), color: darkerCyan,
                 count: 2200, speed: 52, strutCount: 5, strutLen: 0.3...0.7,
                 triBridgeCount: 3)

        addCRing(to: root, major: 1.1, minor: 0.05, start: 0.8, len: .pi * 0.64,
                 tilt: (0.9, 0.4, 0.3), color: darkerCyan,
                 count: 1200, speed: 26, strutCount: 4, strutLen: 0.2...0.5,
                 periodicFlip: true, triBridgeCount: 3)

        addCRing(to: root, major: 1.25, minor: 0.055, start: 3.5, len: .pi * 0.94,
                 tilt: (-0.4, 1.0, -0.5), color: averageCyan,
                 count: 1600, speed: 31, strutCount: 4, strutLen: 0.2...0.6,
                 periodicFlip: true, triBridgeCount: 3)
    }

    // MARK: - O Ring

    private static func addORing(to root: SCNNode) {
        let major: Float = 1.5
        let minor: Float = 0.12

        let verts = makeStructuredTorusVertices(
            majorRadius: major, minorRadius: minor,
            arcStart: 0, arcLength: .pi * 2, count: 3500
        )

        let geo = makePointGeometry(
            vertices: verts, color: darkerCyan, emissionIntensity: 0.03,
            pointSize: 0.004, minScreenSize: 0.5, maxScreenSize: 1.2
        )
        geo.firstMaterial?.shaderModifiers = [.fragment: nanotechShader]

        let arcNode = SCNNode(geometry: geo)

        let struts = makeStrutVertices(
            ringMajor: major, arcStart: 0, arcLength: .pi * 2,
            count: 8, lenRange: 0.2...0.6
        )
        let strutGeo = makePointGeometry(
            vertices: struts.vertices, color: darkerCyan, emissionIntensity: 0.015,
            pointSize: 0.004, minScreenSize: 0.5, maxScreenSize: 1.2
        )
        strutGeo.firstMaterial?.shaderModifiers = [.fragment: strutBuildShader]
        arcNode.addChildNode(SCNNode(geometry: strutGeo))

        let triBridge = makeTriangleBridgeVertices(
            ringMajor: major, arcStart: 0, arcLength: .pi * 2, count: 5
        )
        let triGeo = makePointGeometry(
            vertices: triBridge.vertices, color: darkerCyan, emissionIntensity: 0.01,
            pointSize: 0.004, minScreenSize: 0.5, maxScreenSize: 1.2
        )
        triGeo.firstMaterial?.shaderModifiers = [.fragment: triBridgeShader]
        arcNode.addChildNode(SCNNode(geometry: triGeo))

        let container = SCNNode()
        container.eulerAngles = SCNVector3(Float.pi / 2, 0, 0)
        container.addChildNode(arcNode)

        arcNode.runAction(.repeatForever(.rotateBy(x: 0, y: .pi * 2, z: 0, duration: 50)))
        root.addChildNode(container)
    }

    // MARK: - Road Network Generation

    private static func generateRoadNetwork(
        center: Float, sigma: Float,
        halfW: Float, halfH: Float
    ) -> [RoadSegment] {
        var segments: [RoadSegment] = []
        var endpoints: [(t: Float, r: Float, y: Float)] = []

        let mainCount = Int.random(in: 2...3)
        for _ in 0..<mainCount {
            let halfSpan = Float.random(in: 0.06...0.16)
            let tS = center - halfSpan * Float.random(in: 0.3...1.0)
            let tE = center + halfSpan * Float.random(in: 0.3...1.0)
            let rS = Float.random(in: -halfW * 0.85...halfW * 0.85)
            let rE = Float.random(in: -halfW * 0.85...halfW * 0.85)
            let yS = Float.random(in: -halfH * 0.85...halfH * 0.85)
            let yE = Float.random(in: -halfH * 0.85...halfH * 0.85)
            let thick = Float.random(in: 0.004...0.010)

            let segStart = min(tS, tE)
            let segEnd = max(tS, tE)
            segments.append(RoadSegment(
                tStart: segStart, tEnd: segEnd,
                rStart: rS, rEnd: rE, yStart: yS, yEnd: yE,
                thickness: thick
            ))
            endpoints.append((t: segStart, r: rS, y: yS))
            endpoints.append((t: segEnd, r: rE, y: yE))

            let branchCount = Int.random(in: 2...4)
            for _ in 0..<branchCount {
                let bT = Float.random(in: segStart...segEnd)
                let frac = (bT - segStart) / max(0.001, segEnd - segStart)
                let bR = rS + (rE - rS) * frac
                let bY = yS + (yE - yS) * frac

                let bLen = Float.random(in: 0.02...0.10)
                let bDir: Float = Bool.random() ? 1 : -1
                let bTE = bT + bLen * bDir
                let bRE = Float.random(in: -halfW * 0.85...halfW * 0.85)
                let bYE = Float.random(in: -halfH * 0.85...halfH * 0.85)
                let bThick = Float.random(in: 0.003...0.007)

                let bStart = min(bT, bTE)
                let bEnd = max(bT, bTE)
                let bStartR = bT < bTE ? bR : bRE
                let bEndR = bT < bTE ? bRE : bR
                let bStartY = bT < bTE ? bY : bYE
                let bEndY = bT < bTE ? bYE : bY

                segments.append(RoadSegment(
                    tStart: bStart, tEnd: bEnd,
                    rStart: bStartR, rEnd: bEndR,
                    yStart: bStartY, yEnd: bEndY,
                    thickness: bThick
                ))
                endpoints.append((t: bTE, r: bRE, y: bYE))
            }
        }

        let capCount = Int.random(in: 8...14)
        for _ in 0..<capCount {
            let capLen = Float.random(in: 0.01...0.06)
            let capT = center + Float.random(in: -sigma * 2...sigma * 2)
            let capTE = capT + capLen * (Bool.random() ? 1 : -1)
            let capStart = min(capT, capTE)
            let capEnd = max(capT, capTE)
            let capRs = Float.random(in: -halfW * 0.9...halfW * 0.9)
            let capRe = Float.random(in: -halfW * 0.9...halfW * 0.9)
            let capYs = Float.random(in: -halfH * 0.9...halfH * 0.9)
            let capYe = Float.random(in: -halfH * 0.9...halfH * 0.9)
            segments.append(RoadSegment(
                tStart: capStart, tEnd: capEnd,
                rStart: capRs, rEnd: capRe,
                yStart: capYs, yEnd: capYe,
                thickness: Float.random(in: 0.002...0.005)
            ))
        }

        let crossCount = Int.random(in: 2...5)
        for _ in 0..<crossCount {
            guard endpoints.count >= 2 else { break }
            let a = endpoints.randomElement()!
            let b = endpoints.randomElement()!
            let tDiff = abs(a.t - b.t)
            if tDiff > 0.005 && tDiff < 0.15 {
                let cStart = min(a.t, b.t)
                let cEnd = max(a.t, b.t)
                let cStartR = a.t < b.t ? a.r : b.r
                let cEndR = a.t < b.t ? b.r : a.r
                let cStartY = a.t < b.t ? a.y : b.y
                let cEndY = a.t < b.t ? b.y : a.y
                segments.append(RoadSegment(
                    tStart: cStart, tEnd: cEnd,
                    rStart: cStartR, rEnd: cEndR,
                    yStart: cStartY, yEnd: cEndY,
                    thickness: Float.random(in: 0.002...0.005)
                ))
            }
        }

        return segments
    }

    // MARK: - Structured Torus Vertices

    private static func makeStructuredTorusVertices(
        majorRadius: Float,
        minorRadius: Float,
        arcStart: Float,
        arcLength: Float,
        count: Int
    ) -> [SCNVector3] {
        var vertices: [SCNVector3] = []

        let halfW = minorRadius
        let halfH = minorRadius
        let edgeJitter = minorRadius * 0.15

        let zoneCount = Int.random(in: 5...7)
        var zones: [DenseZone] = []
        for i in 0..<zoneCount {
            let base = (Float(i) + 0.5) / Float(zoneCount)
            let center = max(0.04, min(0.96, base + Float.random(in: -0.06...0.06)))
            let sigma = Float.random(in: 0.04...0.10)
            let peak = Float.random(in: 0.3...0.6)
            let segs = generateRoadNetwork(
                center: center, sigma: sigma,
                halfW: halfW, halfH: halfH
            )
            zones.append(DenseZone(
                center: center, sigma: sigma,
                peakDensity: peak, segments: segs
            ))
        }

        let maxAttempts = count * 25
        var kept = 0

        for _ in 0..<maxAttempts {
            guard kept < count else { break }

            let theta = arcStart + Float.random(in: 0...arcLength)
            let t = (theta - arcStart) / arcLength

            var density: Float = 0.015
            var bestZone: DenseZone? = nil
            var bestContrib: Float = 0
            for zone in zones {
                let dist = t - zone.center
                let g = zone.peakDensity * exp(-(dist * dist) / (2 * zone.sigma * zone.sigma))
                density += g
                if g > bestContrib { bestContrib = g; bestZone = zone }
            }

            let keepProb = min(0.8, density)
            guard Float.random(in: 0...1) < keepProb else { continue }

            var localRadial: Float
            var localY: Float

            let inDenseArea = bestContrib > 0.05

            if inDenseArea, let zone = bestZone {
                let active = zone.segments.filter { t >= $0.tStart && t <= $0.tEnd }
                if let seg = active.randomElement() {
                    let frac = (t - seg.tStart) / max(0.001, seg.tEnd - seg.tStart)
                    localRadial = seg.rStart + (seg.rEnd - seg.rStart) * frac
                        + Float.random(in: -seg.thickness...seg.thickness)
                    localY = seg.yStart + (seg.yEnd - seg.yStart) * frac
                        + Float.random(in: -seg.thickness...seg.thickness)
                } else {
                    if Float.random(in: 0...1) < 0.7 {
                        let cx: Float = Bool.random() ? halfW : -halfW
                        let cy: Float = Bool.random() ? halfH : -halfH
                        localRadial = cx + Float.random(in: -edgeJitter...edgeJitter)
                        localY = cy + Float.random(in: -edgeJitter...edgeJitter)
                    } else {
                        let face = Int.random(in: 0...3)
                        switch face {
                        case 0:
                            localY = halfH + Float.random(in: -edgeJitter...edgeJitter)
                            localRadial = Float.random(in: -halfW...halfW)
                        case 1:
                            localY = -halfH + Float.random(in: -edgeJitter...edgeJitter)
                            localRadial = Float.random(in: -halfW...halfW)
                        case 2:
                            localRadial = halfW + Float.random(in: -edgeJitter...edgeJitter)
                            localY = Float.random(in: -halfH...halfH)
                        default:
                            localRadial = -halfW + Float.random(in: -edgeJitter...edgeJitter)
                            localY = Float.random(in: -halfH...halfH)
                        }
                    }
                }
            } else {
                if Float.random(in: 0...1) < 0.7 {
                    let cx: Float = Bool.random() ? halfW : -halfW
                    let cy: Float = Bool.random() ? halfH : -halfH
                    localRadial = cx + Float.random(in: -edgeJitter...edgeJitter)
                    localY = cy + Float.random(in: -edgeJitter...edgeJitter)
                } else {
                    let face = Int.random(in: 0...3)
                    switch face {
                    case 0:
                        localY = halfH + Float.random(in: -edgeJitter...edgeJitter)
                        localRadial = Float.random(in: -halfW...halfW)
                    case 1:
                        localY = -halfH + Float.random(in: -edgeJitter...edgeJitter)
                        localRadial = Float.random(in: -halfW...halfW)
                    case 2:
                        localRadial = halfW + Float.random(in: -edgeJitter...edgeJitter)
                        localY = Float.random(in: -halfH...halfH)
                    default:
                        localRadial = -halfW + Float.random(in: -edgeJitter...edgeJitter)
                        localY = Float.random(in: -halfH...halfH)
                    }
                }
            }

            let r = majorRadius + localRadial
            vertices.append(SCNVector3(r * cos(theta), localY, r * sin(theta)))
            kept += 1
        }

        return vertices
    }

    // MARK: - Strut Beam Geometry

    private static func makeStrutVertices(
        ringMajor: Float,
        arcStart: Float,
        arcLength: Float,
        count: Int,
        lenRange: ClosedRange<Float>
    ) -> (vertices: [SCNVector3], texcoords: [CGPoint]) {
        var verts: [SCNVector3] = []
        var uvs: [CGPoint] = []
        let baseW: Float = 0.024
        let tipW: Float = 0.010
        let baseH: Float = 0.024
        let tipH: Float = 0.010
        let skin: Float = 0.005

        for _ in 0..<count {
            let theta = arcStart + Float.random(in: 0...arcLength)
            let strutLen = Float.random(in: lenRange)
            let cosT = cos(theta)
            let sinT = sin(theta)

            let tiltTang = Float.random(in: -0.12...0.12)
            let tiltY = Float.random(in: -0.08...0.08)

            let mainRoadCount = Int.random(in: 1...2)
            var roads: [(tangPos: Float, yPos: Float, thick: Float)] = []
            for _ in 0..<mainRoadCount {
                roads.append((
                    tangPos: Float.random(in: -0.6...0.6),
                    yPos: Float.random(in: -0.6...0.6),
                    thick: Float.random(in: 0.003...0.006)
                ))
            }
            let capillaryCount = Int.random(in: 2...4)
            for _ in 0..<capillaryCount {
                roads.append((
                    tangPos: Float.random(in: -0.9...0.9),
                    yPos: Float.random(in: -0.9...0.9),
                    thick: Float.random(in: 0.001...0.003)
                ))
            }

            let n = Int.random(in: 90...150)

            for _ in 0..<n {
                let ext = Float.random(in: 0...strutLen)
                let frac = ext / strutLen

                let w = baseW + (tipW - baseW) * frac
                let h = baseH + (tipH - baseH) * frac

                let tiltOffTang = tiltTang * ext
                let tiltOffY = tiltY * ext

                let r = ringMajor - ext

                var tangOff: Float
                var yOff: Float

                if Float.random(in: 0...1) < 0.6, let road = roads.randomElement() {
                    tangOff = road.tangPos * w + Float.random(in: -road.thick...road.thick)
                    yOff = road.yPos * h + Float.random(in: -road.thick...road.thick)
                } else {
                    let face = Int.random(in: 0...3)
                    switch face {
                    case 0:
                        tangOff = Float.random(in: -w...w)
                        yOff = h - Float.random(in: 0...skin)
                    case 1:
                        tangOff = Float.random(in: -w...w)
                        yOff = -h + Float.random(in: 0...skin)
                    case 2:
                        tangOff = w - Float.random(in: 0...skin)
                        yOff = Float.random(in: -h...h)
                    default:
                        tangOff = -w + Float.random(in: 0...skin)
                        yOff = Float.random(in: -h...h)
                    }
                }

                tangOff += tiltOffTang
                yOff += tiltOffY

                let tanX = -sinT
                let tanZ = cosT
                let x = r * cosT + tangOff * tanX
                let z = r * sinT + tangOff * tanZ
                verts.append(SCNVector3(x, yOff, z))
                uvs.append(CGPoint(x: CGFloat(frac), y: 0))
            }
        }
        return (verts, uvs)
    }

    // MARK: - Triangle Bridge Geometry

    private static func makeTriangleBridgeVertices(
        ringMajor: Float,
        arcStart: Float,
        arcLength: Float,
        count: Int
    ) -> (vertices: [SCNVector3], texcoords: [CGPoint]) {
        var verts: [SCNVector3] = []
        var uvs: [CGPoint] = []
        let nucleusR: Float = 0.35

        for i in 0..<count {
            let base = (Float(i) + 0.5) / Float(count) * arcLength
            let jitterRange = arcLength / Float(count) * 0.35
            let theta = arcStart + base + Float.random(in: -jitterRange...jitterRange)
            let ringX = ringMajor * cos(theta)
            let ringZ = ringMajor * sin(theta)
            let ringY: Float = Float.random(in: -0.02...0.02)

            let convR = ringMajor * Float.random(in: 0.85...0.93)
            let convX = convR * cos(theta) + Float.random(in: -0.02...0.02)
            let convZ = convR * sin(theta) + Float.random(in: -0.02...0.02)
            let convY: Float = Float.random(in: -0.02...0.02)

            let baseT = Float.random(in: 0...Float.pi * 2)
            let baseP = acos(Float.random(in: -0.5...0.5))
            let spreadScale = (ringMajor - 1.0) / 1.6
            let minSpread: Float = 0.12 + spreadScale * 0.25
            let maxSpread: Float = 0.25 + spreadScale * 0.35
            for arm in 0..<2 {
                let spread: Float = Float.random(in: minSpread...maxSpread)
                let nT = baseT + (arm == 0 ? -spread : spread)
                let nP = baseP + Float.random(in: -0.08...0.08)
                let nX = nucleusR * sin(nP) * cos(nT)
                let nY = nucleusR * sin(nP) * sin(nT)
                let nZ = nucleusR * cos(nP)

                let armN = Int.random(in: 65...90)
                for _ in 0..<armN {
                    let t = Float.random(in: 0...1)
                    let x = nX + (convX - nX) * t
                    let y = nY + (convY - nY) * t
                    let z = nZ + (convZ - nZ) * t
                    let jitter: Float = 0.004 * (1.1 - t * 0.3)
                    verts.append(SCNVector3(
                        x + Float.random(in: -jitter...jitter),
                        y + Float.random(in: -jitter...jitter),
                        z + Float.random(in: -jitter...jitter)
                    ))
                    uvs.append(CGPoint(x: 0, y: 0))
                }
            }

            let stemN = Int.random(in: 40...55)
            for _ in 0..<stemN {
                let t = Float.random(in: 0...1)
                let x = convX + (ringX - convX) * t
                let y = convY + (ringY - convY) * t
                let z = convZ + (ringZ - convZ) * t
                let jitter: Float = 0.003
                verts.append(SCNVector3(
                    x + Float.random(in: -jitter...jitter),
                    y + Float.random(in: -jitter...jitter),
                    z + Float.random(in: -jitter...jitter)
                ))
                uvs.append(CGPoint(x: 0, y: 0))
            }
        }
        return (verts, uvs)
    }

    // MARK: - C Ring

    private static func addCRing(
        to parent: SCNNode,
        major: Float, minor: Float,
        start: Float, len: Float,
        tilt: (Float, Float, Float),
        color: UIColor,
        count: Int, speed: Double,
        strutCount: Int, strutLen: ClosedRange<Float>,
        spinDir: CGFloat = 1.0,
        periodicFlip: Bool = false,
        triBridgeCount: Int = 0
    ) {
        let verts = makeStructuredTorusVertices(
            majorRadius: major, minorRadius: minor,
            arcStart: start, arcLength: len, count: count
        )

        let geo = makePointGeometry(
            vertices: verts, color: color, emissionIntensity: 0.03,
            pointSize: 0.004, minScreenSize: 0.5, maxScreenSize: 1.2
        )
        geo.firstMaterial?.shaderModifiers = [.fragment: nanotechShader]

        let arcNode = SCNNode(geometry: geo)

        let struts = makeStrutVertices(
            ringMajor: major, arcStart: start, arcLength: len,
            count: strutCount, lenRange: strutLen
        )
        let strutGeo = makePointGeometry(
            vertices: struts.vertices, color: darkerCyan, emissionIntensity: 0.015,
            pointSize: 0.004, minScreenSize: 0.5, maxScreenSize: 1.2
        )
        strutGeo.firstMaterial?.shaderModifiers = [.fragment: strutBuildShader]
        arcNode.addChildNode(SCNNode(geometry: strutGeo))

        if triBridgeCount > 0 {
            let triBridge = makeTriangleBridgeVertices(
                ringMajor: major, arcStart: start, arcLength: len,
                count: triBridgeCount
            )
            let triGeo = makePointGeometry(
                vertices: triBridge.vertices, color: darkerCyan, emissionIntensity: 0.01,
                pointSize: 0.004, minScreenSize: 0.5, maxScreenSize: 1.2
            )
            triGeo.firstMaterial?.shaderModifiers = [.fragment: triBridgeShader]
            arcNode.addChildNode(SCNNode(geometry: triGeo))
        }

        let container = SCNNode()
        container.eulerAngles = SCNVector3(tilt.0, tilt.1, tilt.2)
        container.addChildNode(arcNode)

        arcNode.runAction(.repeatForever(
            .rotateBy(x: 0, y: .pi * 2 * spinDir, z: 0, duration: speed)
        ))

        if periodicFlip {
            let flipAction = SCNAction.repeatForever(.sequence([
                .wait(duration: 22, withRange: 10),
                .run { node in
                    let rx = CGFloat(Float.random(in: 0.87...1.75))
                    let rz = CGFloat(Float.random(in: 0.3...0.9))
                    node.runAction(.rotateBy(x: rx, y: 0, z: rz, duration: 0.9))
                }
            ]))
            arcNode.runAction(flipAction)
        }

        parent.addChildNode(container)
    }

    // MARK: - Point Cloud Geometry

    private static func makePointGeometry(
        vertices: [SCNVector3],
        color: UIColor,
        emissionIntensity: CGFloat,
        pointSize: CGFloat,
        minScreenSize: CGFloat,
        maxScreenSize: CGFloat
    ) -> SCNGeometry {
        let source = SCNGeometrySource(vertices: vertices)
        let indices = Array(0..<UInt32(vertices.count))
        let element = SCNGeometryElement(indices: indices, primitiveType: .point)
        element.pointSize = pointSize
        element.minimumPointScreenSpaceRadius = minScreenSize
        element.maximumPointScreenSpaceRadius = maxScreenSize

        let geometry = SCNGeometry(sources: [source], elements: [element])
        let material = SCNMaterial()
        material.emission.contents = color
        material.emission.intensity = emissionIntensity
        material.diffuse.contents = UIColor.black
        material.blendMode = .add
        material.writesToDepthBuffer = false
        material.isDoubleSided = true
        geometry.materials = [material]

        return geometry
    }

    // MARK: - Camera

    private static func addCamera(to root: SCNNode) {
        let camera = SCNCamera()
        camera.wantsHDR = true
        camera.bloomIntensity = 0.2
        camera.bloomThreshold = 1.0
        camera.bloomBlurRadius = 4.0
        camera.zNear = 0.1
        camera.zFar = 100.0

        let node = SCNNode()
        node.camera = camera
        node.position = SCNVector3(0, 0.5, 10.0)
        node.look(at: SCNVector3(0, 0, 0))
        root.addChildNode(node)
    }
}
