// Tower — menu bar icon policy.
//
// The menu bar is the Tower radar, rendered exactly like the popover header so
// the two always match. Its state is the guard, distilled (Model.radarState):
//   off      → routing off, unguarded        (red ring, hollow core)
//   holdGeo  → off-country, held pending      (amber ring + fence + blip)
//   holdNet  → no usable path, held pending   (amber ring + sonar pings)
//   verify   → confirming location            (neutral, sweeping)
//   clear    → guarding, path open            (neutral, calm)
// Full color — the amber/red IS the information — with a neutral resolved from
// the menu-bar appearance. The needs-you / usage badge is drawn by AppDelegate.

import AppKit

struct MenubarIcon {
    let image: NSImage?
    let describe: String
}

@MainActor
func menubarIcon(for model: TowerModel, phase: Double) -> MenubarIcon {
    let state = model.radarState
    let awake = model.awakeGlow
    let reduce = NSWorkspace.shared.accessibilityDisplayShouldReduceMotion
    let image = Glyph.radar(state, phase: phase, neutral: Glyph.menubarNeutral(),
                            awake: awake, reduce: reduce)
        ?? NSImage(systemSymbolName: "dot.radiowaves.left.and.right",
                   accessibilityDescription: nil)
    return MenubarIcon(image: image, describe: menubarDescription(for: model))
}

/// The status in words — tooltip and VoiceOver.
@MainActor
func menubarDescription(for model: TowerModel) -> String {
    // The lamp is the only awake signal in the bar — no number, no badge. The
    // tooltip still says it plainly for VoiceOver and on hover.
    let awake = model.awakeGlow
    let awakeSuffix = awake == .clamshell ? " · staying awake (lid closed)"
                    : awake == .idle ? " · staying awake" : ""
    return model.status.title + awakeSuffix
}

/// The bar's badge, as one attributed title beside the radar: the urgent count
/// in a filled pill (the system's own notification-badge language), then the
/// plan % led by a tiny ring that fills with it. Drawn with AppKit into
/// resolution-independent images (drawn lazily at the bar's scale), rebuilt
/// only when the badge's content changes — never per animation frame.
enum MenubarBadge {
    static let font = NSFont.monospacedDigitSystemFont(ofSize: 12, weight: .medium)

    static func title(urgent: Int, failed: Bool, pct: Int?) -> NSAttributedString {
        let s = NSMutableAttributedString(string: " ")
        if urgent > 0 {
            s.append(attachment(pill(urgent, color: failed ? .systemRed : .systemOrange)))
            if pct != nil { s.append(NSAttributedString(string: "  ")) }
        }
        if let pct {
            let color = levelNSColor(pct)
            s.append(attachment(ring(Double(pct) / 100, color: color)))
            s.append(NSAttributedString(string: " \(pct)%", attributes: [
                .font: font, .foregroundColor: color,
            ]))
        }
        return s
    }

    /// Vertically centred on the text's cap height, so pill, ring and digits
    /// share one optical midline.
    private static func attachment(_ image: NSImage) -> NSAttributedString {
        let a = NSTextAttachment()
        a.image = image
        let y = (font.capHeight - image.size.height) / 2
        a.bounds = CGRect(x: 0, y: y.rounded(), width: image.size.width, height: image.size.height)
        return NSAttributedString(attachment: a)
    }

    private static func pill(_ n: Int, color: NSColor) -> NSImage {
        let text = n > 99 ? "99+" : "\(n)"
        let f = NSFont.monospacedDigitSystemFont(ofSize: 10, weight: .bold)
        let attrs: [NSAttributedString.Key: Any] = [.font: f, .foregroundColor: NSColor.white]
        let tw = (text as NSString).size(withAttributes: attrs).width
        let h: CGFloat = 15
        let w = max(h, ceil(tw) + 9)
        return NSImage(size: NSSize(width: w, height: h), flipped: false) { r in
            color.setFill()
            NSBezierPath(roundedRect: r, xRadius: h / 2, yRadius: h / 2).fill()
            let ts = (text as NSString).size(withAttributes: attrs)
            (text as NSString).draw(at: NSPoint(x: (r.width - ts.width) / 2,
                                                y: (r.height - ts.height) / 2 + 0.5),
                                    withAttributes: attrs)
            return true
        }
    }

    private static func ring(_ fraction: Double, color: NSColor) -> NSImage {
        let d: CGFloat = 12, lw: CGFloat = 2.2
        return NSImage(size: NSSize(width: d, height: d), flipped: false) { r in
            let c = NSPoint(x: r.midX, y: r.midY), rad = (d - lw) / 2
            let track = NSBezierPath()
            track.appendArc(withCenter: c, radius: rad, startAngle: 0, endAngle: 360)
            track.lineWidth = lw
            NSColor.labelColor.withAlphaComponent(0.22).setStroke()
            track.stroke()
            let f = min(max(fraction, 0), 1)
            guard f > 0 else { return true }
            let arc = NSBezierPath()
            arc.appendArc(withCenter: c, radius: rad, startAngle: 90,
                          endAngle: 90 - 360 * f, clockwise: true)
            arc.lineWidth = lw
            arc.lineCapStyle = .round
            color.setStroke()
            arc.stroke()
            return true
        }
    }
}

/// Everything a still (phase 0) menu-bar radar depends on. While it's unchanged,
/// the frame already in the bar is exactly the one we would render.
struct StillIconKey: Equatable {
    let state: RadarState
    let awake: AwakeGlow
    let reduce: Bool
    let appearance: NSAppearance.Name
    let scale: CGFloat

    @MainActor init(model: TowerModel) {
        state = model.radarState
        awake = model.awakeGlow
        reduce = NSWorkspace.shared.accessibilityDisplayShouldReduceMotion
        appearance = NSApp.effectiveAppearance.name
        scale = NSScreen.main?.backingScaleFactor ?? 2
    }
}
