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
}

/// Keep-awake, as a soft "vigil" the radar wears on top of any state — the
/// tower's lamp. Dark when sleep is allowed, lit while the Mac is held awake,
/// breathing slowly on a lid-closed vigil. Deliberately NEUTRAL (never amber /
/// red) so a guard hold or an unguarded state always outranks it: the two facts
/// compose in one mark instead of fighting for the same colour.
enum AwakeGlow { case none, idle, clamshell }

// --------------------------------------------------------------------------- //
// Radar geometry — one function, drawn into a context pre-scaled to the 0…100 box.
// --------------------------------------------------------------------------- //
private func circle(_ c: CGPoint, _ r: CGFloat) -> Path {
    Path(ellipseIn: CGRect(x: c.x - r, y: c.y - r, width: r * 2, height: r * 2))
}
private let hub = CGPoint(x: 50, y: 50)

func drawRadar(_ ctx: GraphicsContext, size: CGFloat, state: RadarState,
               phase P: Double, color: Color, awake: AwakeGlow = .none,
               reduce: Bool) {
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

    // ---- keep-awake "vigil": the tower's lamp, layered under the core. off =
    // a plain dark dot; on = a bright core + a breathing neutral halo ring (the
    // readable tell). clamshell breathes deeper so lid-closed reads as "more".
    // Neutral by design — never amber/red — so a guard hold always outranks it.
    if awake != .none {
        // idle = a steady lit lamp; only the lid-closed vigil breathes.
        let breathing = awake == .clamshell
        let live: Double = reduce ? 0 : 1
        let amp = breathing ? 1.0 : 0.6
        let br  = (breathing && live > 0) ? (0.5 + 0.5 * sin(P * 2 * .pi / 2.4)) : 0.7
        for (r, op) in [(CGFloat(15), 0.09), (CGFloat(11), 0.15), (CGFloat(7.5), 0.22)] {
            g0.fill(circle(hub, r), with: .color(color.opacity(op * (0.75 + 0.35 * br * amp))))
        }
        let haloR = 9.5 + 1.7 * br * amp
        g0.stroke(circle(hub, CGFloat(haloR)),
                  with: .color(color.opacity(0.44 + 0.30 * br * amp)),
                  style: StrokeStyle(lineWidth: 2.2))
    }

    // ---- the core -----------------------------------------------------------
    if state == .off {
        g0.stroke(circle(hub, 5.5), with: .color(towerRed), style: StrokeStyle(lineWidth: 4))
    } else {
        g0.fill(circle(hub, awake == .none ? 4.5 : 5.6),
                with: .color(state == .holdNet ? towerAmber : color))
    }
}

// --------------------------------------------------------------------------- //
// Model marks — one monochrome glyph per tier. Still at rest (`energy` 0);
// alive, in the model's own way, while its agent works (`energy` toward 1).
// Deliberately colorless: minimal, the row's accent lives in text alone.
// --------------------------------------------------------------------------- //
func drawModelMark(_ ctx: GraphicsContext, size: CGFloat, tier: ModelTier,
                   color: Color, phase P: Double = 0, energy: Double = 0) {
    let sc = size / 100
    let E = max(0, energy)
    var g0 = ctx
    g0.scaleBy(x: sc, y: sc)
    func stroke(_ ctx: GraphicsContext, _ path: Path, _ w: CGFloat) {
        ctx.stroke(path, with: .color(color), style: StrokeStyle(lineWidth: w, lineCap: .round, lineJoin: .round))
    }
    func rotoscale(_ deg: Double, _ k: Double) -> GraphicsContext {
        var g = g0
        g.translateBy(x: 50, y: 50); g.rotate(by: .degrees(deg)); g.scaleBy(x: k, y: k); g.translateBy(x: -50, y: -50)
        return g
    }

    switch tier {
    case .haiku:
        // The whole mark sways; each tick breathes outward on its own beat.
        let rotAll = E * 6 * sin(P * 0.7)
        let g = rotoscale(rotAll, 1)
        for k in 0..<3 {
            let a = (-90 + Double(k) * 120) * .pi / 180, dx = cos(a), dy = sin(a)
            let osc = 0.5 + 0.5 * sin(P * 2.3 + Double(k) * 2.094)
            let off = E * 3.4 * osc
            var p = Path()
            p.move(to: CGPoint(x: 50 + dx * (16 + off), y: 50 + dy * (16 + off)))
            p.addLine(to: CGPoint(x: 50 + dx * (34 + off), y: 50 + dy * (34 + off)))
            stroke(g, p, 8)
        }
        let cs = 1 + E * 0.22 * sin(P * 3.0)
        g.fill(circle(hub, 7 * cs), with: .color(color))

    case .sonnet:
        // A slow, continuous turn.
        let rot = E * (P * 16) + E * 4 * sin(P * 1.3)
        let s = 1 + E * 0.05 * sin(P * 1.3)
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
        stroke(rotoscale(rot, s), p, 8)

    case .opus:
        // Three rings orbiting at their own rates; the core pulses.
        let radii = [16.0, 27.0, 38.0], gaps = [90.0, 210.0, 330.0], rates = [14.0, -10.0, 8.0]
        for i in 0..<3 {
            let rr = E * (P * rates[i]), s = 1 + E * 0.06 * sin(P * 1.7 - Double(i) * 0.8)
            var p = Path()
            for j in 0...48 {                   // a 300° arc, open at the gap
                let a = (gaps[i] + 30 + Double(j) / 48 * 300) * .pi / 180
                let pt = CGPoint(x: 50 + radii[i] * cos(a), y: 50 + radii[i] * sin(a))
                if j == 0 { p.move(to: pt) } else { p.addLine(to: pt) }
            }
            stroke(rotoscale(rr, s), p, 6.5)
        }
        let cs = 1 + E * 0.18 * sin(P * 2.1)
        g0.fill(circle(hub, 5 * cs), with: .color(color))

    case .fable, .other:
        // A highlight winds up the spiral.
        let steps = 120
        func spiral(_ f: Double) -> CGPoint {
            let ang = f * 2.35 * 2 * .pi - .pi / 2, rr = 2.5 + (35 - 2.5) * f
            return CGPoint(x: 50 + rr * cos(ang), y: 50 + rr * sin(ang))
        }
        var base = Path()
        for i in 0...steps { let p = spiral(Double(i) / Double(steps)); if i == 0 { base.move(to: p) } else { base.addLine(to: p) } }
        stroke(g0, base, 8)
        if E > 0.01 {
            let head = (P * 0.22).truncatingRemainder(dividingBy: 1)
            let tail = max(0, head - 0.16)
            var seg = Path()
            var first = true
            var f = tail
            while f <= head { let p = spiral(f); if first { seg.move(to: p); first = false } else { seg.addLine(to: p) }; f += 0.01 }
            g0.stroke(seg, with: .color(color.opacity(min(1, E) * 0.95)),
                      style: StrokeStyle(lineWidth: 8.6, lineCap: .round, lineJoin: .round))
            g0.fill(circle(spiral(head), 5), with: .color(color.opacity(min(1, E))))
        }
        g0.fill(circle(hub, 4), with: .color(color))
    }
}

// --------------------------------------------------------------------------- //
// Beacon — the keep-awake mark for the popover row and the dashboard card. The
// tower's lamp, standalone (no radar ring): a hollow, dim lamp when sleep is
// allowed; a lit lamp with a breathing halo while the Mac is held awake. Same
// neutral vigil language as the radar core, so one glow reads the same
// everywhere. Drawn in the shared 0…100 box.
// --------------------------------------------------------------------------- //
func drawBeacon(_ ctx: GraphicsContext, size: CGFloat, mode: AwakeGlow,
                phase P: Double, color: Color, reduce: Bool) {
    let sc = size / 100
    var g0 = ctx
    g0.scaleBy(x: sc, y: sc)
    let on = mode != .none
    let breathing = mode == .clamshell
    let live: Double = reduce ? 0 : 1
    let amp = breathing ? 1.0 : 0.6
    let br  = (breathing && live > 0) ? (0.5 + 0.5 * sin(P * 2 * .pi / 2.4)) : 0.7
    if on {
        for (r, op) in [(CGFloat(30), 0.10), (CGFloat(21), 0.17), (CGFloat(13), 0.26)] {
            g0.fill(circle(hub, r), with: .color(color.opacity(op * (0.75 + 0.35 * br * amp))))
        }
        let ringR = 17 + 2 * br * amp
        g0.stroke(circle(hub, CGFloat(ringR)),
                  with: .color(color.opacity(0.30 + 0.25 * br * amp)),
                  style: StrokeStyle(lineWidth: 4.5))
        g0.fill(circle(hub, 11), with: .color(color))
    } else {
        g0.stroke(circle(hub, 15), with: .color(color.opacity(0.34)),
                  style: StrokeStyle(lineWidth: 4.5))
        g0.fill(circle(hub, 6), with: .color(color.opacity(0.30)))
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
    var awake: AwakeGlow = .none
    var animated: Bool = true
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        // Animate while the state has motion to spend frames on, OR while the
        // Mac is on a lid-closed vigil (the lamp breathes). A still context
        // (animated:false) still shows a static *lit* lamp when awake.
        let live = (animated || awake == .clamshell) && !reduceMotion
        TimelineView(.animation(minimumInterval: 1.0 / 60, paused: !live)) { tl in
            Canvas { ctx, sz in
                drawRadar(ctx, size: sz.width, state: state,
                          phase: live ? tl.date.timeIntervalSinceReferenceDate : 0,
                          color: color, awake: awake, reduce: reduceMotion)
            }
            .frame(width: size, height: size)
        }
    }
}

/// A monochrome model mark. Still at rest; smoothly alive while `working`.
struct ModelGlyphView: View {
    let tier: ModelTier
    var working: Bool = false
    var size: CGFloat = TowerDesign.Size.rowGlyph
    var color: Color = .primary
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        let live = working && !reduceMotion
        TimelineView(.animation(minimumInterval: 1.0 / 60, paused: !live)) { tl in
            Canvas { ctx, sz in
                drawModelMark(ctx, size: sz.width, tier: tier, color: color,
                              phase: live ? tl.date.timeIntervalSinceReferenceDate : 0,
                              energy: live ? 1 : 0)
            }
            .frame(width: size, height: size)
        }
    }
}

/// The keep-awake lamp as a live view. Breathes only while the Mac is held
/// awake (idle or clamshell); a still, dim ring when sleep is allowed. Reduce
/// Motion freezes it at a legible lit frame.
struct BeaconView: View {
    var mode: AwakeGlow
    var size: CGFloat = 26
    var color: Color = .primary
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        // Only the lid-closed vigil breathes; idle is a still, lit lamp.
        let live = mode == .clamshell && !reduceMotion
        TimelineView(.animation(minimumInterval: 1.0 / 60, paused: !live)) { tl in
            Canvas { ctx, sz in
                drawBeacon(ctx, size: sz.width, mode: mode,
                           phase: live ? tl.date.timeIntervalSinceReferenceDate : 0,
                           color: color, reduce: reduceMotion)
            }
            .frame(width: size, height: size)
        }
    }
}

// --------------------------------------------------------------------------- //
// Menu-bar radar — baked to a full-color NSImage per frame so it reads exactly
// like the popover: brand amber/red for the state, a neutral (resolved from the
// menu-bar appearance) for everything else. NOT a template — the colors ARE the
// information (amber hold vs red unguarded), so we never let AppKit flatten them.
// --------------------------------------------------------------------------- //
enum Glyph {
    @MainActor static func radar(_ state: RadarState, phase: Double,
                                 neutral: Color, awake: AwakeGlow = .none,
                                 reduce: Bool) -> NSImage? {
        let pt = TowerDesign.Size.menubarPt
        let view = Canvas { ctx, sz in
            drawRadar(ctx, size: sz.width, state: state, phase: phase,
                      color: neutral, awake: awake, reduce: reduce)
        }
        .frame(width: pt, height: pt)
        let r = ImageRenderer(content: view)
        r.scale = NSScreen.main?.backingScaleFactor ?? 2
        guard let img = r.nsImage else { return nil }
        img.isTemplate = false
        return img
    }

    /// The menu bar's foreground color, resolved for its current appearance —
    /// matches the popover's `.primary` so the two radars line up.
    @MainActor static func menubarNeutral() -> Color {
        let ea = NSApp.effectiveAppearance
        var resolved = NSColor.labelColor
        ea.performAsCurrentDrawingAppearance {
            resolved = NSColor.labelColor.usingColorSpace(.sRGB) ?? .labelColor
        }
        return Color(nsColor: resolved)
    }
}
