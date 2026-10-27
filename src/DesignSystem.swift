// Tower — design system tokens.
//
// Philosophy: "Quiet tower, clear signal." A well-run tower is calm. Motion is
// information: agents work in a steady rhythm, and exactly one thing at a
// time is allowed to call for you.
//   1. The mark is alive only when its model is thinking; still otherwise.
//   2. Motion = state change — celebration is earned (done), never granted
//      (failure is sober). Nothing loops at full attention when all is well.
//   3. One loudest thing — a strict attention hierarchy.

import AppKit
import SwiftUI

enum TowerDesign {
    /// Tower's one interactive color: white on dark, near-black on light —
    /// never the system blue. Switches, selections, rings, charts and primary
    /// buttons all wear it; amber/red stay reserved for holds and danger.
    static let ink = Color(nsColor: NSColor(name: "TowerInk") { a in
        a.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
            ? NSColor(white: 0.92, alpha: 1) : NSColor(white: 0.14, alpha: 1)
    })
    /// A switch that's on is green — the one place Tower borrows a system
    /// color for an interactive state, because "on" should read at a glance.
    static let switchOn = Color(nsColor: .systemGreen)
    /// Text/glyph drawn ON the ink (a filled primary button's label).
    static let onInk = Color(nsColor: NSColor(name: "TowerOnInk") { a in
        a.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
            ? NSColor(white: 0.08, alpha: 1) : NSColor(white: 0.98, alpha: 1)
    })

    enum Motion {
        /// Any state swap (colors, symbols, toggles).
        static let settle  = Animation.spring(response: 0.45, dampingFraction: 0.85)
        /// Entrances — rows and glyphs arriving (slight overshoot).
        static let arrive  = Animation.spring(response: 0.55, dampingFraction: 0.72)
        /// The done payoff — checkmark pop.
        static let payoff  = Animation.spring(response: 0.35, dampingFraction: 0.60)
        /// Failure — never bounces.
        static let sober   = Animation.easeOut(duration: 0.25)
        /// Needs-you queue re-ranking / agent list reordering.
        static let reorder = Animation.spring(response: 0.50, dampingFraction: 0.80)
        /// Seconds per shimmer sweep on an in-flight activity line.
        static let shimmerPeriod: Double = 1.8
        /// Stagger per row on multi-row inserts.
        static let stagger: Double = 0.04
        /// How long the done-glow holds before settling.
        static let glowHold: Double = 0.9
    }

    enum Size {
        static let popoverWidth: CGFloat = 360
        static let menubarPt: CGFloat = 18
        static let rowGlyph: CGFloat = 28
        static let radiusCard: CGFloat = 10
        static let radiusBadge: CGFloat = 6
        static let padH: CGFloat = 14
        static let rowVPad: CGFloat = 7
    }

    // Type scale: header 13 semibold · row title 13 · activity 11 secondary ·
    // times/counters 11 monospacedDigit · section headers 11 semibold secondary.
    enum Font {
        static let header = SwiftUI.Font.system(size: 13, weight: .semibold)
        static let rowTitle = SwiftUI.Font.system(size: 13)
        static let activity = SwiftUI.Font.system(size: 11)
        static let counter = SwiftUI.Font.system(size: 11).monospacedDigit()
        static let section = SwiftUI.Font.system(size: 11, weight: .semibold)
        static let caption = SwiftUI.Font.system(size: 9)

        /// JetBrains Mono — bundled in Resources/Fonts and registered at launch
        /// (see AppDelegate.registerBundledFonts). Referenced by PostScript name;
        /// falls back to the system monospaced face if registration ever fails,
        /// so text is never lost. Used for the technical model/effort tokens.
        static func mono(_ size: CGFloat, bold: Bool = false) -> SwiftUI.Font {
            let name = bold ? "JetBrainsMono-Bold" : "JetBrainsMono-Medium"
            return NSFont(name: name, size: size) != nil
                ? .custom(name, size: size)
                : .system(size: size, weight: bold ? .bold : .medium, design: .monospaced)
        }
    }
}

// Reduce Motion: every animated view checks this and degrades — loops stop,
// springs become short fades, count-ups set directly.
struct MotionAware: ViewModifier {
    @Environment(\.accessibilityReduceMotion) var reduce
    func body(content: Content) -> some View { content }
}

extension Animation {
    /// The token, unless Reduce Motion is on — then a quiet fade.
    static func tower(_ token: Animation, reduced: Bool) -> Animation {
        reduced ? .easeInOut(duration: 0.2) : token
    }
}

// --------------------------------------------------------------------------- //
// Status → attention semantics. Done-vs-failed is unmistakable without color:
// distinct symbol shapes + fixed queue positions + distinct motion.
// --------------------------------------------------------------------------- //
enum AgentStatus: String {
    case working, pendingTool = "pending_tool", waitingInput = "waiting_input"
    case asking, done, failed, idle, gone, paused

    init(raw: String?) { self = AgentStatus(rawValue: raw ?? "") ?? .idle }

    var symbol: String {
        switch self {
        case .failed:       return "xmark.octagon.fill"
        case .pendingTool:  return "hand.raised.fill"
        case .asking:       return "questionmark.bubble.fill"
        case .done, .waitingInput: return "checkmark.circle"
        case .working:      return "gearshape"
        case .paused:       return "pause.circle"
        case .idle, .gone:  return "zzz"
        }
    }
    var color: Color {
        switch self {
        case .failed:       return Color(nsColor: .systemRed)
        case .pendingTool:  return Color(nsColor: .systemOrange)
        case .asking:       return Color(nsColor: .systemIndigo)
        case .done, .waitingInput: return Color(nsColor: .systemGreen)
        case .working:      return .primary
        case .paused, .idle, .gone: return Color(nsColor: .tertiaryLabelColor)
        }
    }
    var phrase: String {
        switch self {
        case .working:      return "working"
        case .pendingTool:  return "waiting for approval"
        case .asking:       return "asked you a question"
        case .done, .waitingInput: return "done — your turn"
        case .failed:       return "failed"
        case .paused:       return "paused"
        case .idle:         return "resting"
        case .gone:         return "gone"
        }
    }
    /// Needs-you rank: failed loudest, done quietest. nil = not in the queue.
    var needsYouRank: Int? {
        switch self {
        case .failed: return 0
        case .pendingTool: return 1
        case .asking: return 2
        case .done, .waitingInput: return 3
        default: return nil
        }
    }
}

// Model tier — each model has its own living mark. Order matters (highest first).
enum ModelTier: String, CaseIterable, Comparable {
    case fable, opus, sonnet, haiku, other

    init(family: String?) { self = ModelTier(rawValue: family ?? "") ?? .other }
    init(modelID: String?) {
        let s = (modelID ?? "").lowercased()
        if s.contains("fable") { self = .fable }
        else if s.contains("opus") { self = .opus }
        else if s.contains("sonnet") { self = .sonnet }
        else if s.contains("haiku") { self = .haiku }
        else { self = .other }
    }

    var rank: Int {
        switch self {
        case .fable: return 4; case .opus: return 3
        case .sonnet: return 2; case .haiku: return 1; case .other: return 0
        }
    }
    static func < (a: ModelTier, b: ModelTier) -> Bool { a.rank < b.rank }

    var display: String {
        switch self {
        case .fable: return "Fable"; case .opus: return "Opus"
        case .sonnet: return "Sonnet"; case .haiku: return "Haiku"
        case .other: return "Other"
        }
    }
    /// Tier accent — colors the model's mark; never the sole signal.
    var accent: Color {
        switch self {
        case .fable:  return Color(red: 0.788, green: 0.635, blue: 0.153) // #C9A227 gold
        case .opus:   return Color(red: 0.690, green: 0.204, blue: 0.235) // #B0343C rosso
        case .sonnet: return Color(red: 0.231, green: 0.435, blue: 0.710) // #3B6FB5 steel
        case .haiku:  return Color(red: 0.910, green: 0.518, blue: 0.173) // #E8842C crayon
        case .other:  return .gray
        }
    }
}

// --------------------------------------------------------------------------- //
// Popover composition — app-local prefs (UserDefaults). Shared keys/defaults so
// the Settings panel that WRITES them and the popover that READS them can never
// drift. Defaults reproduce today's full popover for anyone who never opens
// Settings. Registered once at launch (AppDelegate.registerDefaults).
// --------------------------------------------------------------------------- //
enum PopPref {
    static let net = "pop.net"
    static let agents = "pop.agents"
    static let location = "pop.location"
    static let keepawake = "pop.keepawake"
    static let plan = "pop.plan"
    static let apps = "pop.apps"
    static let resting = "pop.resting"
    static let density = "pop.density"        // "comfy" | "compact"
    static let needsBadge = "mb.needsBadge"   // menu-bar needs-you count on/off
    /// Section order, comma-separated PopSection ids — dragged in Settings.
    static let order = "pop.order"
    // Finer details inside sections.
    static let planStyle = "pop.planStyle"    // "rings" | "bars"
    static let subagents = "pop.subagents"    // subagent trees under working rows
    static let ip = "pop.ip"                  // public IP on the location row
    // Which plan limits you track — popover rings, dashboard, menu-bar "closest".
    static let limitSession = "plan.session"
    static let limitWeek = "plan.week"
    static let limitFable = "plan.fable"

    static let defaultOrder = "net,agents,location,apps,keepawake,plan"

    /// The launch defaults — the full popover for anyone who never opens
    /// Settings: every section on in attention order, comfortable, resting
    /// shown (collapsed), the needs-you badge on.
    static let defaults: [String: Any] = [
        // Claude apps start hidden: most people only run Claude Code, and Tower
        // sees no live activity from Desktop or the web — switch it on in Settings.
        net: true, agents: true, location: true, keepawake: true, plan: true, apps: false,
        resting: true, density: "comfy", needsBadge: true, order: defaultOrder,
        planStyle: "rings", subagents: true, ip: true,
        limitSession: true, limitWeek: true, limitFable: true,
    ]

    /// The plan limits the user tracks, as (label, bucket) in display order.
    static func trackedLimits(_ p: GPlan?) -> [(label: String, bucket: GPlanBucket?)] {
        let d = UserDefaults.standard
        var out: [(String, GPlanBucket?)] = []
        if d.bool(forKey: limitSession) { out.append(("Session", p?.session)) }
        if d.bool(forKey: limitWeek) { out.append(("Weekly", p?.week)) }
        if d.bool(forKey: limitFable) { out.append(("Fable", p?.fable)) }
        return out
    }
}

/// The popover's movable middle sections. The header (guard) and footer stay
/// put; everything between is yours to order and show.
enum PopSection: String, CaseIterable, Identifiable {
    case net, agents, location, apps, keepawake, plan
    var id: String { rawValue }
    var title: String {
        switch self {
        case .net: return "Network weather"; case .agents: return "Agents"
        case .location: return "Location"; case .apps: return "Claude apps"
        case .keepawake: return "Keep awake"; case .plan: return "Plan usage"
        }
    }
    var detail: String {
        switch self {
        case .net:       return "Latency to the internet and Anthropic, and any fault"
        case .agents:    return "Needs you, collisions, working agents, resting"
        case .location:  return "Where the fence thinks you are"
        case .apps:      return "Open Desktop or claude.ai through the guard"
        case .keepawake: return "The lamp and the sleep switch"
        case .plan:      return "Session, weekly and Fable rings"
        }
    }
    var symbol: String {
        switch self {
        case .net: return "wifi"; case .agents: return "dot.radiowaves.left.and.right"
        case .location: return "location"; case .apps: return "macwindow"
        case .keepawake: return "cup.and.saucer"; case .plan: return "gauge.with.dots.needle.33percent"
        }
    }
    var visibilityKey: String {
        switch self {
        case .net: return PopPref.net; case .agents: return PopPref.agents
        case .location: return PopPref.location; case .apps: return PopPref.apps
        case .keepawake: return PopPref.keepawake; case .plan: return PopPref.plan
        }
    }
    /// Parse a stored order: unknown ids dropped, missing sections appended,
    /// so a new section (or a hand-edited default) never vanishes.
    static func order(_ raw: String) -> [PopSection] {
        var out: [PopSection] = []
        for id in raw.split(separator: ",") {
            if let s = PopSection(rawValue: String(id)), !out.contains(s) { out.append(s) }
        }
        return out + allCases.filter { !out.contains($0) }
    }
}

// Row density for the popover, read by every flat section via the environment
// so a single toggle re-tunes them all without threading a parameter through.
private struct PopoverCompactKey: EnvironmentKey { static let defaultValue = false }
extension EnvironmentValues {
    var popoverCompact: Bool {
        get { self[PopoverCompactKey.self] }
        set { self[PopoverCompactKey.self] = newValue }
    }
}

// Whether the surface hosting this view is on screen. The popover and dashboard
// stay mounted while closed, and a TimelineView / repeatForever animation inside
// them keeps drawing frames nobody can see — so every continuous motion (model
// marks, radar, beacon, shimmer, spinners) runs only while this is true.
// Motion = state change: a hidden mark has nothing to say.
private struct SurfaceVisibleKey: EnvironmentKey { static let defaultValue = true }
extension EnvironmentValues {
    var surfaceVisible: Bool {
        get { self[SurfaceVisibleKey.self] }
        set { self[SurfaceVisibleKey.self] = newValue }
    }
}

/// Every Tower switch: the native switch, green when on — set at each surface's
/// root so plain `Toggle`s (Form rows included) pick it up, while pickers,
/// menus and selections keep the white ink.
struct TowerSwitchStyle: ToggleStyle {
    func makeBody(configuration: Configuration) -> some View {
        Toggle(configuration).toggleStyle(SwitchToggleStyle()).tint(TowerDesign.switchOn)
    }
}
extension ToggleStyle where Self == TowerSwitchStyle {
    static var tower: TowerSwitchStyle { TowerSwitchStyle() }
}

/// How a row enters and leaves any Tower list: it fades in while dropping a
/// few points into place, and leaves by fading as it settles — while the rows
/// around it glide on the list's spring, so the stack never jumps. Under
/// Reduce Motion it is a plain fade.
extension AnyTransition {
    static func towerRow(reduced: Bool = false) -> AnyTransition {
        if reduced { return .opacity }
        return .asymmetric(
            insertion: .opacity
                .combined(with: .offset(y: -6))
                .combined(with: .scale(scale: 0.97, anchor: .top)),
            removal: .opacity
                .combined(with: .scale(scale: 0.97, anchor: .top)))
    }
}

extension View {
    /// A list row: the shared enter/leave transition, honoring Reduce Motion.
    func towerRow() -> some View { modifier(TowerRowTransition()) }
}

private struct TowerRowTransition: ViewModifier {
    @Environment(\.accessibilityReduceMotion) private var reduced
    func body(content: Content) -> some View {
        content.transition(.towerRow(reduced: reduced))
    }
}
