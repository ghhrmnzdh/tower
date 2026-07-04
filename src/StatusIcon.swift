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
    let reduce = NSWorkspace.shared.accessibilityDisplayShouldReduceMotion
    let image = Glyph.radar(state, phase: phase, neutral: Glyph.menubarNeutral(), reduce: reduce)
        ?? NSImage(systemSymbolName: "dot.radiowaves.left.and.right",
                   accessibilityDescription: nil)
    return MenubarIcon(image: image, describe: model.status.title)
}
