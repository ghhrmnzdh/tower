// Tower — menu bar icon policy.
//
// The menu bar is the Tower radar. Its state is the guard, distilled
// (Model.radarState):
//   off      → routing off, unguarded        (red)
//   holdGeo  → off-country, held pending      (amber)
//   holdNet  → no usable path, held pending   (amber)
//   verify   → confirming location            (monochrome, sweeping)
//   clear    → guarding, path open            (monochrome, calm)
// The image is a monochrome template; tint carries the alert level (red for
// unguarded, amber for a hold), nothing else. The needs-you / usage badge is
// drawn beside it by AppDelegate.

import AppKit

struct MenubarIcon {
    let image: NSImage?
    let tint: NSColor?
    let describe: String
}

@MainActor
func menubarIcon(for model: TowerModel, phase: Double) -> MenubarIcon {
    let state = model.radarState
    let reduce = NSWorkspace.shared.accessibilityDisplayShouldReduceMotion
    let image = Glyph.radar(state, phase: phase, reduce: reduce)
        ?? NSImage(systemSymbolName: "dot.radiowaves.left.and.right",
                   accessibilityDescription: nil)
    return MenubarIcon(image: image, tint: state.tint, describe: model.status.title)
}
