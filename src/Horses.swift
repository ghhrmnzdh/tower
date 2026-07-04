// Corral — horse asset loading. One horse per model tier, craft scales with
// caliber (crayon → flat vector → sculpted badge → gilded myth). SVGs live in
// Resources/horses/ and load straight into NSImage (macOS 11+ CoreSVG);
// loader falls back .svg → .pdf, then to an SF Symbol so a missing asset
// never blanks the menu bar.

import AppKit
import SwiftUI

enum Horses {
    private static var cache: [String: NSImage] = [:]

    private static func load(_ name: String) -> NSImage? {
        if let img = cache[name] { return img }
        guard let res = Bundle.main.resourcePath else { return nil }
        for ext in ["svg", "pdf"] {
            let path = "\(res)/horses/\(name).\(ext)"
            if FileManager.default.fileExists(atPath: path),
               let img = NSImage(contentsOfFile: path) {
                cache[name] = img
                return img
            }
        }
        return nil
    }

    /// Full-color master for popover rows and detail views.
    static func color(_ tier: HorseTier, pt: CGFloat = CorralDesign.Size.rowHorse) -> NSImage? {
        let base = tier == .other ? "sonnet" : tier.rawValue
        guard let img = load(base) else { return nil }
        let sized = img.copy() as! NSImage
        // Masters are 120×90 — keep the aspect, fit to `pt` height.
        sized.size = NSSize(width: pt * (4.0 / 3.0), height: pt)
        return sized
    }

    /// Monochrome template for the menu bar (tier legible from silhouette).
    /// `step` renders the subtle canter frame (0.6pt lift) used while a tool
    /// call is in flight — quiet enough to read as breathing, not a gif.
    static func menubarTemplate(_ tier: HorseTier, step: Bool = false) -> NSImage? {
        let base = (tier == .other ? "sonnet" : tier.rawValue) + "-template"
        return template(named: base, step: step)
    }

    /// The horseshoe — Corral's mark when the corral is empty.
    static func horseshoe() -> NSImage? { template(named: "horseshoe-template") }

    private static func template(named name: String, step: Bool = false) -> NSImage? {
        let key = step ? "\(name)#step" : name
        if let img = cache[key] { return img }
        guard let src = load(name) else { return nil }
        let pt = CorralDesign.Size.menubarPt
        let img = NSImage(size: NSSize(width: pt, height: pt), flipped: false) { rect in
            var dest = rect
            if step { dest.origin.y += 0.6 }   // canter lift
            src.draw(in: dest)
            return true
        }
        img.isTemplate = true
        cache[key] = img
        return img
    }
}

/// SwiftUI wrapper: a tier horse avatar (color), SF-symbol fallback.
struct HorseAvatar: View {
    let tier: HorseTier
    var pt: CGFloat = CorralDesign.Size.rowHorse
    var body: some View {
        if let img = Horses.color(tier, pt: pt) {
            Image(nsImage: img)
                .resizable()
                .aspectRatio(contentMode: .fit)
                .frame(width: pt * (4.0 / 3.0), height: pt)
        } else {
            Image(systemName: "figure.equestrian.sports")
                .font(.system(size: pt * 0.6, weight: .medium))
                .foregroundStyle(tier.accent)
                .frame(width: pt * (4.0 / 3.0), height: pt)
        }
    }
}
