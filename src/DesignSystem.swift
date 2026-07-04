// Corral — design system tokens.
//
// Philosophy: "Fine tack, calm hands." A well-run stable is quiet. Motion is
// information: the herd works in a calm rhythm, and exactly one thing at a
// time is allowed to call for the rancher.
//   1. Craft = caliber — the finer the model, the finer the art.
//   2. Motion = state change — celebration is earned (done), never granted
//      (failure is sober). Nothing loops at full attention when all is well.
//   3. One loudest thing — a strict attention hierarchy.

import SwiftUI

enum CorralDesign {
    enum Motion {
        /// Any state swap (colors, symbols, toggles).
        static let settle  = Animation.spring(response: 0.45, dampingFraction: 0.85)
        /// Entrances — rows and horses arriving (slight overshoot).
        static let arrive  = Animation.spring(response: 0.55, dampingFraction: 0.72)
        /// The done payoff — checkmark pop.
        static let payoff  = Animation.spring(response: 0.35, dampingFraction: 0.60)
        /// Failure — never bounces.
        static let sober   = Animation.easeOut(duration: 0.25)
        /// Needs-you queue re-ranking / herd reordering.
        static let reorder = Animation.spring(response: 0.50, dampingFraction: 0.80)
        /// The working horse breathes.
        static let breathe = Animation.easeInOut(duration: 2.4).repeatForever(autoreverses: true)
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
        static let rowHorse: CGFloat = 28
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
    static func corral(_ token: Animation, reduced: Bool) -> Animation {
        reduced ? .easeInOut(duration: 0.2) : token
    }
}

// --------------------------------------------------------------------------- //
// Status → attention semantics. Done-vs-failed is unmistakable without color:
// distinct symbol shapes + fixed queue positions + distinct motion.
// --------------------------------------------------------------------------- //
enum AgentStatus: String {
    case working, pendingTool = "pending_tool", waitingInput = "waiting_input"
    case asking, done, failed, idle, gone

    init(raw: String?) { self = AgentStatus(rawValue: raw ?? "") ?? .idle }

    var symbol: String {
        switch self {
        case .failed:       return "xmark.octagon.fill"
        case .pendingTool:  return "hand.raised.fill"
        case .asking:       return "questionmark.bubble.fill"
        case .done, .waitingInput: return "checkmark.circle"
        case .working:      return "figure.equestrian.sports"
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
        case .idle, .gone:  return Color(nsColor: .tertiaryLabelColor)
        }
    }
    var phrase: String {
        switch self {
        case .working:      return "working"
        case .pendingTool:  return "waiting for approval"
        case .asking:       return "asked you a question"
        case .done, .waitingInput: return "done — your turn"
        case .failed:       return "failed"
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

// Model tier — craft scales with caliber. Order matters (highest first).
enum HorseTier: String, CaseIterable, Comparable {
    case fable, opus, sonnet, haiku, other

    init(family: String?) { self = HorseTier(rawValue: family ?? "") ?? .other }
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
    static func < (a: HorseTier, b: HorseTier) -> Bool { a.rank < b.rank }

    var display: String {
        switch self {
        case .fable: return "Fable"; case .opus: return "Opus"
        case .sonnet: return "Sonnet"; case .haiku: return "Haiku"
        case .other: return "Mustang"
        }
    }
    /// Tier accent — used in the popover only, never as the sole signal.
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
