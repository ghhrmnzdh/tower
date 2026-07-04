// Tower — the identity marks, ported from "Tower Identity Study.html".
//
// Two families, one geometry language (a 0…100 box, a center, and the lines
// that move around it):
//
//   · The RADAR — Tower's status mark. Five states that map 1:1 onto the guard:
//       clear   → guarding, path open      (calm pulse, live blips)
//       verify  → confirming location      (a sweep rotates)
//       holdNet → no usable path, pending  (amber dashed ring, sonar pings)
//       holdGeo → off-country, pending     (amber fence + an off-country blip)
//       off     → routing off, UNGUARDED   (red dashed ring, hollow core)
//     Motion is a function of (state, time). Reduce Motion freezes each state
//     at a legible still frame — never a blank.
//
//   · The MODEL MARKS — one still glyph per model tier (haiku ticks, sonnet S,
//     opus rings, fable spiral), colored by the tier accent.
//
// The same draw functions back the live SwiftUI views (Canvas + TimelineView)
// and the menu-bar templates (Canvas rasterized once per frame by ImageRenderer)
// so there is exactly one source of truth for every pixel.

import AppKit
import SwiftUI

// Brand accents from the study.
private let towerAmber = Color(red: 0xE6 / 255, green: 0xA9 / 255, blue: 0x3C / 255)
private let towerRed   = Color(red: 0xE5 / 255, green: 0x48 / 255, blue: 0x4D / 255)
let TowerAmberNS = NSColor(red: 0xE6 / 255, green: 0xA9 / 255, blue: 0x3C / 255, alpha: 1)
let TowerRedNS   = NSColor(red: 0xE5 / 255, green: 0x48 / 255, blue: 0x4D / 255, alpha: 1)

// --------------------------------------------------------------------------- //
// Radar state — the guard, distilled to five looks.
// --------------------------------------------------------------------------- //
enum RadarState {
    case clear, verify, holdNet, holdGeo, off

    /// Menu-bar tint (template images tint uniformly). nil = default label color.
    var tint: NSColor? {
        switch self {
        case .off: return TowerRedNS
        case .holdNet, .holdGeo: return TowerAmberNS
        case .clear, .verify: return nil
        }
    }
    /// Whether this state carries motion worth animating in the menu bar.
    var animates: Bool {
        switch self { case .clear: return false; default: return true } // clear pulses; gate on agents in AppDelegate
    }
}

// --------------------------------------------------------------------------- //
// Radar geometry — one function, drawn into a context pre-scaled to the 0…100 box.
// --------------------------------------------------------------------------- //
private func circle(_ c: CGPoint, _ r: CGFloat) -> Path {
    Path(ellipseIn: CGRect(x: c.x - r, y: c.y - r, width: r * 2, height: r * 2))
}
private let hub = CGPoint(x: 50, y: 50)

func drawRadar(_ ctx: GraphicsContext, size: CGFloat, state: RadarState,
               phase P: Double, color: Color, reduce: Bool) {
    let sc = size / 100
    var g0 = ctx
    g0.scaleBy(x: sc, y: sc)            // everything below is in 0…100 units
    let A: Double = reduce ? 0 : 1

    // rotate a context copy about the hub, hand it to `draw`
    func rotated(_ deg: Double, _ draw: (GraphicsContext) -> Void) {
        var g = g0
        g.translateBy(x: 50, y: 50); g.rotate(by: .degrees(deg)); g.translateBy(x: -50, y: -50)
        draw(g)
    }

    // ---- outer ring: color + dash encode the state --------------------------
    let ringColor: Color
    var ringDash: [CGFloat] = []
    switch state {
    case .off:      ringColor = towerRed;   ringDash = [5, 7]
    case .holdNet:  ringColor = towerAmber;  ringDash = [5, 6]
    case .holdGeo:  ringColor = towerAmber
    default:        ringColor = color
    }
    g0.stroke(circle(hub, 33), with: .color(ringColor),
              style: StrokeStyle(lineWidth: 6, dash: ringDash))

    // ---- verify: a rotating sweep with a soft trail -------------------------
    if state == .verify {
        rotated((P * 150).truncatingRemainder(dividingBy: 360)) { g in
            var trail = Path()
            trail.move(to: hub)
            let a0 = 270.0, a1 = 208.5
            for i in 0...12 {
                let a = (a0 + (a1 - a0) * Double(i) / 12) * .pi / 180
                trail.addLine(to: CGPoint(x: 50 + 33 * cos(a), y: 50 + 33 * sin(a)))
            }
            trail.closeSubpath()
            g.fill(trail, with: .color(color.opacity(0.16)))
            var line = Path(); line.move(to: hub); line.addLine(to: CGPoint(x: 50, y: 17))
            g.stroke(line, with: .color(color), style: StrokeStyle(lineWidth: 4, lineCap: .round))
        }
    }

    // ---- clear: a slow radar pulse -----------------------------------------
    if state == .clear {
        let pr = A > 0 ? (P * 0.42).truncatingRemainder(dividingBy: 1) : 0
        let r  = A > 0 ? 8 + pr * 26 : 22
        let op = A > 0 ? (1 - pr) * 0.5 : 0.3
        g0.stroke(circle(hub, CGFloat(r)), with: .color(color.opacity(op)),
                  style: StrokeStyle(lineWidth: 3))
    }

    // ---- holdNet: amber sonar pings ----------------------------------------
    if state == .holdNet {
        for i in 0..<2 {
            let pr = A > 0 ? ((P * 0.7) + Double(i) * 0.5).truncatingRemainder(dividingBy: 1) : 0
            let r  = A > 0 ? 7 + pr * 15 : 11 + Double(i) * 7
            let op = A > 0 ? max(0, 1 - pr) * 0.7 : 0.55 - Double(i) * 0.25
            g0.stroke(circle(hub, CGFloat(r)), with: .color(towerAmber.opacity(op)),
                      style: StrokeStyle(lineWidth: 3.5))
        }
    }

    // ---- blips: contacts on the scope --------------------------------------
    let blips = [CGPoint(x: 64, y: 41), CGPoint(x: 38, y: 58), CGPoint(x: 58, y: 66)]
    for (i, b) in blips.enumerated() {
        let op: Double
        switch state {
        case .clear:  op = 0.8 + 0.2 * sin(P * 1.6 + Double(i) * 1.3) * A
        case .verify: op = 0.3 + 0.12 * sin(P * 2.2 + Double(i)) * A
        case .off:    op = 0.22
        default:      op = 0
        }
        if op > 0.001 { g0.fill(circle(b, 3.6), with: .color(color.opacity(op))) }
    }

    // ---- holdGeo: a rotating fence + a lunging off-country blip -------------
    if state == .holdGeo {
        rotated((P * 45).truncatingRemainder(dividingBy: 360)) { g in
            g.stroke(circle(hub, 15), with: .color(towerAmber),
                     style: StrokeStyle(lineWidth: 3, dash: [4, 5]))
        }
        var offLine = Path(); offLine.move(to: hub); offLine.addLine(to: CGPoint(x: 72, y: 32))
        g0.stroke(offLine, with: .color(towerAmber),
                  style: StrokeStyle(lineWidth: 2.5, lineCap: .round, dash: [2, 4]))
        let dx = -0.773, dy = 0.634
        let lunge = A > 0 ? 6 * (0.5 + 0.5 * sin(P * 2.2)) : 0
        let s = 1 + (A > 0 ? 0.16 * sin(P * 3.0) : 0)
        let mx = 72 + dx * lunge, my = 32 + dy * lunge
        var gm = g0
        gm.translateBy(x: CGFloat(mx), y: CGFloat(my))
        gm.scaleBy(x: CGFloat(s), y: CGFloat(s))
        gm.translateBy(x: -72, y: -32)
        gm.fill(circle(CGPoint(x: 72, y: 32), 5), with: .color(towerAmber))
        let hp  = A > 0 ? (P * 1.1).truncatingRemainder(dividingBy: 1) : 0
        let hr  = A > 0 ? 5 + hp * 9 : 10
        let hop = A > 0 ? (1 - hp) * 0.8 : 0.5
        g0.stroke(circle(CGPoint(x: CGFloat(mx), y: CGFloat(my)), CGFloat(hr)),
                  with: .color(towerAmber.opacity(hop)), style: StrokeStyle(lineWidth: 2.5))
    }

    // ---- the core -----------------------------------------------------------
    if state == .off {
        g0.stroke(circle(hub, 5.5), with: .color(towerRed), style: StrokeStyle(lineWidth: 4))
    } else {
        g0.fill(circle(hub, 4.5), with: .color(state == .holdNet ? towerAmber : color))
    }
}

// --------------------------------------------------------------------------- //
// Model marks — one still glyph per tier.
// --------------------------------------------------------------------------- //
func drawModelMark(_ ctx: GraphicsContext, size: CGFloat, tier: ModelTier, color: Color) {
    let sc = size / 100
    var g = ctx
    g.scaleBy(x: sc, y: sc)
    func stroke(_ path: Path, _ w: CGFloat) {
        g.stroke(path, with: .color(color), style: StrokeStyle(lineWidth: w, lineCap: .round, lineJoin: .round))
    }
    switch tier {
    case .haiku:
        for k in 0..<3 {
            let a = (-90 + Double(k) * 120) * .pi / 180, dx = cos(a), dy = sin(a)
            var p = Path()
            p.move(to: CGPoint(x: 50 + dx * 16, y: 50 + dy * 16))
            p.addLine(to: CGPoint(x: 50 + dx * 34, y: 50 + dy * 34))
            stroke(p, 8)
        }
        g.fill(circle(hub, 7), with: .color(color))

    case .sonnet:
        var p = Path()
        for i in 0...24 {                       // upper arc, bulges right
            let a = (-90 + Double(i) / 24 * 180) * .pi / 180
            let pt = CGPoint(x: 50 + 12.5 * cos(a), y: 37.5 + 12.5 * sin(a))
            if i == 0 { p.move(to: pt) } else { p.addLine(to: pt) }
        }
        for i in 0...24 {                       // lower arc, bulges left
            let a = (-90 - Double(i) / 24 * 180) * .pi / 180
            p.addLine(to: CGPoint(x: 50 + 12.5 * cos(a), y: 62.5 + 12.5 * sin(a)))
        }
        stroke(p, 8)

    case .opus:
        let radii = [16.0, 27.0, 38.0], gaps = [90.0, 210.0, 330.0]
        for i in 0..<3 {
            var p = Path()
            for j in 0...48 {                   // a 300° arc, open at the gap
                let a = (gaps[i] + 30 + Double(j) / 48 * 300) * .pi / 180
                let pt = CGPoint(x: 50 + radii[i] * cos(a), y: 50 + radii[i] * sin(a))
                if j == 0 { p.move(to: pt) } else { p.addLine(to: pt) }
            }
            stroke(p, 6.5)
        }
        g.fill(circle(hub, 5), with: .color(color))

    case .fable, .other:
        var p = Path()
        let steps = 120
        for i in 0...steps {
            let f = Double(i) / Double(steps)
            let ang = f * 2.35 * 2 * .pi - .pi / 2, rr = 2.5 + (35 - 2.5) * f
            let pt = CGPoint(x: 50 + rr * cos(ang), y: 50 + rr * sin(ang))
            if i == 0 { p.move(to: pt) } else { p.addLine(to: pt) }
        }
        stroke(p, 8)
        g.fill(circle(hub, 4), with: .color(color))
    }
}

// --------------------------------------------------------------------------- //
// Live SwiftUI views.
// --------------------------------------------------------------------------- //

/// The radar, animating while `animated` (and Reduce Motion is off).
struct TowerRadar: View {
    var state: RadarState
    var size: CGFloat = 22
    var color: Color = .primary
    var animated: Bool = true
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        let live = animated && !reduceMotion
        TimelineView(.animation(minimumInterval: 1.0 / 60, paused: !live)) { tl in
            Canvas { ctx, sz in
                drawRadar(ctx, size: sz.width, state: state,
                          phase: live ? tl.date.timeIntervalSinceReferenceDate : 0,
                          color: color, reduce: reduceMotion)
            }
            .frame(width: size, height: size)
        }
    }
}

/// A still model mark, colored by the tier accent.
struct ModelGlyphView: View {
    let tier: ModelTier
    var size: CGFloat = TowerDesign.Size.rowGlyph
    var color: Color? = nil

    var body: some View {
        Canvas { ctx, sz in
            drawModelMark(ctx, size: sz.width, tier: tier, color: color ?? tier.accent)
        }
        .frame(width: size, height: size)
    }
}

// --------------------------------------------------------------------------- //
// Menu-bar templates — the radar, baked to a monochrome NSImage per frame.
// --------------------------------------------------------------------------- //
enum Glyph {
    /// Radar for the menu bar at an explicit phase. Monochrome (isTemplate) so
    /// AppKit tints it to the bar; the caller sets contentTintColor per state.
    @MainActor static func radar(_ state: RadarState, phase: Double, reduce: Bool) -> NSImage? {
        let pt = TowerDesign.Size.menubarPt
        let view = Canvas { ctx, sz in
            drawRadar(ctx, size: sz.width, state: state, phase: phase, color: .black, reduce: reduce)
        }
        .frame(width: pt, height: pt)
        let r = ImageRenderer(content: view)
        r.scale = NSScreen.main?.backingScaleFactor ?? 2
        guard let img = r.nsImage else { return nil }
        img.isTemplate = true
        return img
    }
}
