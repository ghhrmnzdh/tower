// Corral — menu bar icon policy.
//
// The menu bar is a live signal with a strict priority order:
//   1. Network faults (offline / captive / API issue) — weather beats herd;
//      when Claude errors, the bar itself must show where the fault is.
//   2. Guard actively blocking Claude (outside the target country).
//   3. The highest-tier horse among agents at work — which caliber of model
//      is running right now. Canter frame alternates while a tool is in flight.
//   4. The horseshoe — the corral is quiet.
// Tints: red only for net-offline/failed, orange only for blocking. Everything
// else stays template-monochrome (HIG: menu extras are quiet).

import AppKit

struct MenubarIcon {
    let image: NSImage?
    let tint: NSColor?
    let describe: String
}

func menubarIcon(for model: CorralModel, canterStep: Bool) -> MenubarIcon {
    // 1 — network faults first.
    switch model.netStatus {
    case .offline:
        return MenubarIcon(image: symbol("wifi.slash"), tint: .systemRed,
                           describe: "Internet offline")
    case .captive:
        return MenubarIcon(image: symbol("wifi.exclamationmark"), tint: .systemOrange,
                           describe: "Wi-Fi login required")
    case .apiIssue:
        return MenubarIcon(image: symbol("exclamationmark.icloud"), tint: .systemOrange,
                           describe: "Anthropic API unreachable")
    case .degraded:
        return MenubarIcon(image: symbol("wifi.exclamationmark"), tint: nil,
                           describe: "Connection is slow")
    default:
        break
    }

    // 2 — the guard actively blocking (off-country, or fail-closed while still
    // confirming location). Net-fault blocking is already shown at priority 1.
    if model.status == .blocking || model.status == .locating {
        return MenubarIcon(image: symbol(model.status.symbol),
                           tint: .systemOrange, describe: model.status.title)
    }

    // 3 — the herd: highest-tier horse at work.
    if let tier = model.topTierWorking,
       let horse = Horses.menubarTemplate(tier, step: canterStep) {
        return MenubarIcon(image: horse, tint: nil,
                           describe: "\(tier.display) at work — \(model.status.title)")
    }

    // 4 — quiet corral.
    if let shoe = Horses.horseshoe() {
        return MenubarIcon(image: shoe, tint: nil, describe: model.status.title)
    }
    // Asset missing → SF fallback, never a blank status item.
    return MenubarIcon(image: symbol("horseshoe") ?? symbol("shield"), tint: nil,
                       describe: model.status.title)
}

private func symbol(_ name: String) -> NSImage? {
    NSImage(systemSymbolName: name, accessibilityDescription: nil)?
        .withSymbolConfiguration(.init(pointSize: 13.5, weight: .medium))
}
