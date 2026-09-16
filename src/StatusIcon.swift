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
