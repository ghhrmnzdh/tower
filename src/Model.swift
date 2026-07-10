// Tower — model layer: paths, state.json decodables, the polling model,
// and small formatting helpers shared by every view.

import AppKit
import SwiftUI
import Combine

// --------------------------------------------------------------------------- //
// Paths (mirror towerd.py)
// --------------------------------------------------------------------------- //
enum Paths {
    static let home = FileManager.default.homeDirectoryForCurrentUser
    static let dir = home.appendingPathComponent(".tower")
    static let state = dir.appendingPathComponent("state.json")
    static let cmd = dir.appendingPathComponent("cmd")
}

// --------------------------------------------------------------------------- //
// Decodable model — matches build_state() in towerd.py
// --------------------------------------------------------------------------- //
struct GLocation: Decodable {
    var status: String?
    var ip: String?
    var city: String?
    var region: String?
    var country_name: String?
    var country_cc: String?
    var in_target: Bool?
    var isp: String?
    var error: String?
}

struct GGuard: Decodable {
    var target_cc: String?
    var enforce: Bool?
    var block_all: Bool?
    var allowed: Int?
    var blocked: Int?
    var proxy_port: Int?
    var proxy_up: Bool?
    var claude_allowed: Bool?   // fail-closed gate: is a Claude request permitted?
    var net_ok: Bool?           // usable path to Anthropic right now?
    var pending: Bool?          // a Claude request is held/retrying on the guard
    var holding: Int?           // Claude requests parked in-proxy right now
}

struct GRouting: Decodable { var installed: Bool?; var intended: Bool? }
struct GKeepawake: Decodable { var on: Bool?; var mode: String? }
struct GSettings: Decodable { var theme: String?; var country: String?; var plan_week_tokens: Int?; var plan_enabled: Bool? }

struct GSession: Decodable {
    var tokens: Int?; var input: Int?; var output: Int?; var cache: Int?
    var cost: Double?; var msgs: Int?; var since: Double?
}
struct GBucket: Decodable { var tokens: Int?; var cost: Double? }
struct GPace: Decodable {
    var tokens_per_active_hr: Int?; var active_hrs: Int?
    var projected_week_tokens: Int?; var projected_week_cost: Double?
    var live_tpm: Int?
}
struct GHeadroom: Decodable { var used_week_tokens: Int?; var plan_week_tokens: Int?; var pct: Double? }
struct GModel: Decodable, Identifiable {
    var model: String; var tokens: Int; var cost: Double; var pct: Double
    var id: String { model }
}
struct GDay: Decodable, Identifiable {
    var day: String; var tokens: Int; var cost: Double
    var id: String { day }
}
struct GUsage: Decodable {
    var session: GSession?
    var today: GBucket?
    var week: GBucket?
    var pace: GPace?
    var headroom: GHeadroom?
    var byModel: [GModel]?
    var series: [GDay]?
}

// Real plan usage — mirrors `claude -p /usage` (Settings → Usage page).
struct GPlanBucket: Decodable {
    var pct: Int?
    var resets: String?
    var resets_at: Double?

    /// Live relative reset time, no timezone — "in 3h", "in 2d", "now".
    /// Falls back to the raw stamp with the "(timezone)" trimmed off.
    var resetDisplay: String? {
        if let at = resets_at {
            let s = at - Date().timeIntervalSince1970
            if s <= 30 { return "now" }
            if s < 5400 { return "in \(max(1, Int(s / 60)))m" }
            if s < 129_600 { return "in \(Int(s / 3600))h" }
            return "in \(Int(s / 86_400))d"
        }
        guard let r = resets, !r.isEmpty else { return nil }
        return r.replacingOccurrences(of: #"\s*\([^)]*\)\s*$"#, with: "",
                                      options: .regularExpression)
    }
}
struct GLast24h: Decodable { var requests: Int?; var sessions: Int? }
struct GPlan: Decodable {
    var ok: Bool?
    var updated: Double?
    var stale: Bool?
    var refreshing: Bool?
    var disabled: Bool?
    var gated: Bool?            // /usage withheld: guard not passing
    var gate_reason: String?   // "net" | "geo"
    var error: String?
    var session: GPlanBucket?
    var week: GPlanBucket?
    var fable: GPlanBucket?
    var last24h: GLast24h?
}

// Live traffic feed events (published by the daemon, deque of 50).
struct GEvent: Decodable {
    var t: String?; var host: String?; var kind: String?; var action: String?
}

struct GProcs: Decodable { var daemon_pid: Int?; var keepawake_pid: Int? }

// ---- Network health (daemon `net` key) — all optional so the app runs
// against an older daemon that doesn't publish it yet. ---- //
struct GNetSample: Decodable {
    var t: Double?; var internet_ms: Double?; var api_ms: Double?
}
struct GSpeedtest: Decodable {
    var running: Bool?; var progress: Double?; var mbps_down: Double?
    var ms: Double?; var bytes: Int?; var at: Double?; var error: String?
    var cooldown_until: Double?
}
struct GNet: Decodable {
    var status: String?          // checking|online|degraded|offline|api_issue|captive
    var raw_status: String?
    var reason: String?
    var internet_ms: Double?
    var api_ms: Double?
    var api_error: String?
    var last_change: Double?
    var checked: Double?
    var history: [GNetSample]?
    var speedtest: GSpeedtest?
}

enum NetStatus: String {
    case checking, online, degraded, offline, apiIssue = "api_issue", captive
    case unknown
    init(raw: String?) { self = NetStatus(rawValue: raw ?? "") ?? .unknown }
}

// ---- Agent monitoring (daemon `agents` key) ---- //
struct GTicks: Decodable {
    var tools_done: Int?; var files: Int?; var errors: Int?; var subagents: Int?
}
struct GHealth: Decodable { var level: String?; var reasons: [String]? }
struct GPendingTool: Decodable { var name: String?; var detail: String?; var since: Double? }
struct GAgentSession: Decodable, Identifiable {
    var session_id: String?
    var pid: Int?
    var kind: String?            // interactive|background|infra
    var model: String?
    var model_family: String?    // fable|opus|sonnet|haiku|other
    var effort: String?          // low|medium|high|xhigh|max (nil = unknown)
    var context: String?         // context-window tag, e.g. "1M" (nil = default)
    var project_name: String?
    var cwd: String?
    var git_root: String?
    var git_branch: String?
    var title: String?
    var last_prompt: String?
    var status: String?          // working|pending_tool|waiting_input|asking|done|failed|idle|gone
    var status_since: Double?
    var activity: String?
    var pending_tool: GPendingTool?
    var tty: String?
    var focusable: Bool?
    var guarded: Bool?           // true routed, false started-before-guard, nil unknown
    var last_activity: Double?
    var started: Double?
    var ticks: GTicks?
    var health: GHealth?
    var dismissed: Bool?
    var id: String { session_id ?? "\(pid ?? 0)" }

    var tier: ModelTier { ModelTier(family: model_family) }

    /// Full model name — version parsed from the id and the context-window tag
    /// appended when present: "Opus 4.8 · 1M", "Sonnet 5", "Haiku 4.5". Falls
    /// back to the bare tier name when there's no id/version.
    var modelDisplay: String {
        let base = tier.display
        var out = base
        if let raw = model?.lowercased() {
            // drop any bracketed suffix ("claude-opus-4-8[1m]" → "claude-opus-4-8")
            let id = raw.split(separator: "[").first.map(String.init) ?? raw
            // numeric runs, dropping any 6+ digit run (a yyyymmdd date suffix)
            let nums = id.split { !$0.isNumber }.map(String.init).filter { $0.count < 6 }
            if !nums.isEmpty { out = "\(base) \(nums.joined(separator: "."))" }
        }
        if let c = context, !c.isEmpty { out += " · \(c)" }
        return out
    }

    /// The effort chip label, upper-cased ("HIGH", "XHIGH", "ULTRA"). nil hides it.
    var effortLabel: String? {
        guard let e = effort?.trimmingCharacters(in: .whitespaces), !e.isEmpty
        else { return nil }
        return e.uppercased()
    }
}
struct GNeedsYou: Decodable, Identifiable {
    var session_id: String?; var reason: String?; var since: Double?
    var id: String { session_id ?? "?" }
}
struct GCollision: Decodable, Identifiable {
    var git_root: String?; var session_ids: [String]?
    var level: String?; var files: [String]?
    var id: String { git_root ?? "?" }
}
struct GAgentSummary: Decodable {
    var working: Int?; var needs_you: Int?; var done_today: Int?; var top_tier: String?
    var unguarded: Int?          // started before the guard, routing on
    var pinned: Int?             // still proxy-pinned, routing off
}
struct GAgentEvent: Decodable {
    var t: Double?; var session_id: String?; var from: String?; var to: String?
}
struct GAgentsMeta: Decodable {
    var lsof_ok: Bool?; var parse_errors: Int?; var claude_versions: [String]?
}
struct GAgents: Decodable {
    var sessions: [GAgentSession]?
    var needs_you: [GNeedsYou]?
    var collisions: [GCollision]?
    var summary: GAgentSummary?
    var events: [GAgentEvent]?
    var meta: GAgentsMeta?
}

struct GState: Decodable {
    var ts: Double?
    var location: GLocation?
    var guardInfo: GGuard?
    var routing: GRouting?
    var keepawake: GKeepawake?
    var settings: GSettings?
    var usage: GUsage?
    var plan: GPlan?
    var recent: [GEvent]?
    var net: GNet?
    var agents: GAgents?
    var procs: GProcs?
    var version: String?

    enum CodingKeys: String, CodingKey {
        case ts, location, routing, keepawake, settings, usage, plan, recent, net, agents, procs, version
        case guardInfo = "guard"      // `guard` is a Swift keyword
    }
}

// Customizable colour thresholds (shared by the menu bar + popover).
func warnAt() -> Int { let v = UserDefaults.standard.integer(forKey: "warnAt"); return v == 0 ? 60 : v }
func dangerAt() -> Int { let v = UserDefaults.standard.integer(forKey: "dangerAt"); return v == 0 ? 85 : v }

// Usage level → colour: white (low) → yellow (mid) → red (near the limit).
func levelColor(_ pct: Int) -> Color {
    pct >= dangerAt() ? .red : (pct >= warnAt() ? .yellow : .primary)
}
func levelNSColor(_ pct: Int) -> NSColor {
    pct >= dangerAt() ? .systemRed : (pct >= warnAt() ? .systemYellow : .labelColor)
}

// --------------------------------------------------------------------------- //
// Overall guard status
// --------------------------------------------------------------------------- //
enum GuardStatus {
    case starting          // no fresh daemon state yet
    case protected         // routed + in target country + stable net
    case blocking          // routed + confirmed outside target (Claude blocked)
    case unstable          // routed + no usable path to Anthropic (Claude blocked)
    case locating          // routed + location not confirmed (fail-CLOSED → blocked)
    case unrouted          // daemon up but Claude not routed through the guard
    case monitor           // enforcement off — watching only

    var symbol: String {
        switch self {
        case .starting:        return "shield"
        case .protected:       return "checkmark.shield.fill"
        case .blocking:        return "exclamationmark.shield.fill"
        case .unstable:        return "wifi.exclamationmark"
        case .locating:        return "shield.lefthalf.filled"
        case .unrouted:        return "shield.slash"
        case .monitor:         return "eye"
        }
    }
    var tint: NSColor {
        switch self {
        case .protected:       return .systemGreen
        case .blocking:        return .systemOrange
        case .unstable:        return .systemOrange
        case .locating:        return .systemOrange
        case .unrouted:        return .secondaryLabelColor
        case .monitor:         return .systemBlue
        case .starting:        return .secondaryLabelColor
        }
    }
    var title: String {
        switch self {
        case .starting:        return "Starting…"
        case .protected:       return "Protected"
        case .blocking:        return "Blocking Claude"
        case .unstable:        return "Blocking — connection unstable"
        case .locating:        return "Blocking — confirming location…"
        case .unrouted:        return "Not routed"
        case .monitor:         return "Monitor only"
        }
    }
    var swiftUIColor: Color { Color(tint) }
}

// A pending dangerous action (turn guard off / quit). Presented as a
// destructive alert; a second one follows before `perform` runs.
struct DangerRequest: Identifiable {
    let id = UUID()
    let title: String
    let message: String
    let confirmLabel: String
    let perform: () -> Void
}

// --------------------------------------------------------------------------- //
// Model: polls state.json, exposes it, sends commands
// --------------------------------------------------------------------------- //
final class TowerModel: ObservableObject {
    @Published var state: GState?
    @Published var alive = false          // daemon producing fresh state?

    private var timer: Timer?

    func start() {
        refresh()
        timer = Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { [weak self] _ in
            self?.refresh()
        }
    }

    func refresh() {
        guard let data = try? Data(contentsOf: Paths.state),
              let s = try? JSONDecoder().decode(GState.self, from: data) else {
            alive = false
            return
        }
        // "alive" = state stamped within the last 5 seconds.
        let age = Date().timeIntervalSince1970 - (s.ts ?? 0)
        alive = age < 5.0
        state = s
    }

    var status: GuardStatus {
        guard alive, let s = state else { return .starting }
        let routed = s.routing?.installed ?? false
        let enforce = s.guardInfo?.enforce ?? true
        if !routed { return .unrouted }
        if !enforce { return .monitor }
        // Fail-closed: the daemon is the source of truth for whether a Claude
        // request is allowed right now. If it is, we're protected; otherwise
        // report WHY it's blocking (unstable net > unconfirmed location >
        // off-country) so the status stays honest.
        if s.guardInfo?.claude_allowed == true { return .protected }
        if s.guardInfo?.net_ok == false { return .unstable }
        let locStatus = s.location?.status ?? "CHECKING"
        if locStatus != "OK" { return .locating }
        return .blocking   // confirmed OK location, but not the target country
    }

    /// A Claude request is parked on the guard right now — held in-proxy or
    /// retrying — waiting for a healthy path. Drives the shimmering
    /// "reconnecting" indicator; the daemon flips it false the instant the
    /// guard passes, so the shimmer clears exactly as Claude resumes.
    var retryPending: Bool {
        guard alive else { return false }
        return state?.guardInfo?.pending == true
    }

    /// When the guard isn't passing Claude, `/usage` is withheld (running it
    /// would itself be an off-country / unstable request). Returns the
    /// (headline, detail) to show INSTEAD of usage meters — distinguishing an
    /// internet/connection fault from a location/VPN fault — or nil when usage
    /// should render normally.
    var usageGate: (headline: String, detail: String)? {
        // Explicitly disabled is a separate, existing message — not a gate.
        if state?.plan?.disabled == true { return nil }
        let gated = state?.plan?.gated == true
            || state?.guardInfo?.claude_allowed == false
        guard gated else { return nil }
        let target = state?.guardInfo?.target_cc
            ?? state?.settings?.country ?? "your country"
        // Is it the connection, or the location/VPN? Prefer the daemon's own
        // gate_reason; fall back to net_ok.
        let netFault = state?.plan?.gate_reason == "net"
            || state?.guardInfo?.net_ok == false
        if netFault {
            return ("Usage paused — connection unstable",
                    "Can’t reach Anthropic right now. Check your internet "
                    + "connection or VPN. Usage returns on its own once the "
                    + "link is stable.")
        }
        return ("Usage paused — location not confirmed",
                "You appear to be outside \(target). If you’re on a VPN, set "
                + "it to \(target). Usage returns once your location is "
                + "confirmed.")
    }

    // ---- Dangerous-action double confirmation ------------------------------ //
    // Turning routing off, disabling enforcement, or quitting all let Claude
    // reach the API WITHOUT the guard. These are gated behind a two-stage
    // confirmation (see DangerRequest); the wording escalates when agents are
    // working right now. AppKit flows (quit) do their own two-step NSAlert.
    @Published var danger1: DangerRequest?   // first confirmation
    @Published var danger2: DangerRequest?   // final "are you sure" confirmation

    /// Agents actively working right now — an unguarded switch-off hits them.
    var agentsWorking: Int { workingAgents.count }

    func requestDanger(_ title: String, _ message: String,
                       confirm: String, perform: @escaping () -> Void) {
        danger2 = nil
        danger1 = DangerRequest(title: title, message: message,
                                confirmLabel: confirm, perform: perform)
    }
    func confirmDangerStage1() { danger2 = danger1; danger1 = nil }
    func confirmDangerStage2() { let p = danger2?.perform; danger2 = nil; p?() }
    func cancelDanger() { danger1 = nil; danger2 = nil }

    // ---- Derived agent views (shared by popover, dashboard, icon, notifier) ---- //

    var netStatus: NetStatus { NetStatus(raw: state?.net?.status) }

    /// The guard, distilled to a radar look for the menu bar and header.
    var radarState: RadarState {
        switch status {
        case .unrouted: return .off
        case .blocking: return .holdGeo
        case .unstable: return .holdNet
        case .locating, .starting: return .verify
        case .protected, .monitor:
            // A live net fault still reads as a held connection.
            switch netStatus {
            case .offline, .captive, .apiIssue: return .holdNet
            default: return .clear
            }
        }
    }

    /// Keep-awake, distilled to a lamp glow for the radar + beacon. Orthogonal
    /// to the guard state — the Mac can be held awake in any of them.
    var awakeGlow: AwakeGlow {
        guard state?.keepawake?.on == true else { return .none }
        return state?.keepawake?.mode == "clamshell" ? .clamshell : .idle
    }
    /// "off" | "idle" | "clamshell" — the effective keep-awake mode.
    var keepAwakeMode: String {
        (state?.keepawake?.on == true ? state?.keepawake?.mode : nil) ?? "off"
    }

    /// Sessions worth showing (daemon already excludes "infra").
    var agentSessions: [GAgentSession] { state?.agents?.sessions ?? [] }

    /// The needs-you queue, ranked failed > blocked > asking > done,
    /// oldest first within a rank. Dismissed rows are already excluded
    /// daemon-side; filter again defensively.
    var needsYou: [GAgentSession] {
        agentSessions
            .filter { AgentStatus(raw: $0.status).needsYouRank != nil && $0.dismissed != true }
            .sorted {
                let ra = AgentStatus(raw: $0.status).needsYouRank ?? 9
                let rb = AgentStatus(raw: $1.status).needsYouRank ?? 9
                if ra != rb { return ra < rb }
                return ($0.status_since ?? 0) < ($1.status_since ?? 0)
            }
    }

    /// Agents at work right now (working / pending grace).
    var workingAgents: [GAgentSession] {
        agentSessions
            .filter { AgentStatus(raw: $0.status) == .working }
            .sorted { ModelTier(family: $0.model_family) > ModelTier(family: $1.model_family) }
    }

    /// Resting: idle sessions, collapsed by default.
    var resting: [GAgentSession] {
        agentSessions.filter {
            let st = AgentStatus(raw: $0.status)
            return st == .idle || st == .gone
        }
    }

    var collisions: [GCollision] { state?.agents?.collisions ?? [] }

    /// Highest-tier model among agents at work — the menu bar mark.
    var topTierWorking: ModelTier? {
        let working = agentSessions.filter {
            let st = AgentStatus(raw: $0.status)
            return st == .working || st == .pendingTool
        }
        return working.map { ModelTier(family: $0.model_family) }.max()
    }

    var needsYouCount: Int { needsYou.count }

    /// The user's routing INTENT (vs `installed`, the settings.json file truth).
    /// Falls back to the file truth for a daemon that predates the field.
    var routingIntended: Bool {
        state?.routing?.intended ?? state?.routing?.installed ?? false
    }
    /// Live agents started before the guard while routing is on — restart them to
    /// protect them. Trust the daemon's summary; re-derive defensively as a floor.
    var unguardedCount: Int {
        guard routingIntended else { return 0 }
        if let n = state?.agents?.summary?.unguarded { return n }
        return agentSessions.filter { $0.guarded == false && $0.pid != nil
            && $0.kind != "infra" && $0.status != "gone" }.count
    }
    /// Live agents still guarded by a proxy the user has since turned off — they
    /// keep working until restarted. Only meaningful while routing is off.
    var pinnedCount: Int {
        guard !routingIntended else { return 0 }
        if let n = state?.agents?.summary?.pinned { return n }
        return agentSessions.filter { $0.guarded == true && $0.pid != nil
            && $0.kind != "infra" && $0.status != "gone" }.count
    }
    /// Live agents currently reaching the API THROUGH Tower's proxy (regardless of
    /// routing intent). They lose their connection until restarted if the guard
    /// stops — used to warn on quit.
    var proxyPinnedCount: Int {
        agentSessions.filter { $0.guarded == true && $0.pid != nil
            && $0.kind != "infra" && $0.status != "gone" }.count
    }

    var anyFailed: Bool { needsYou.contains { AgentStatus(raw: $0.status) == .failed } }
    /// True while at least one agent has a tool call in flight (menu-bar breath).
    var anyTooling: Bool {
        agentSessions.contains {
            AgentStatus(raw: $0.status) == .working && $0.pending_tool != nil
        }
    }

    // Fire-and-forget command. Written atomically (temp → rename) so the
    // daemon's watcher never reads a half-written file.
    func send(_ cmd: [String: Any]) {
        try? FileManager.default.createDirectory(at: Paths.cmd, withIntermediateDirectories: true)
        guard let data = try? JSONSerialization.data(withJSONObject: cmd) else { return }
        let id = UUID().uuidString
        let tmp = Paths.cmd.appendingPathComponent(".\(id).tmp")
        let dst = Paths.cmd.appendingPathComponent("\(id).json")
        do {
            try data.write(to: tmp)
            try FileManager.default.moveItem(at: tmp, to: dst)
        } catch { try? FileManager.default.removeItem(at: tmp) }
        // Nudge the UI: state.json will reflect the change within ~1s anyway.
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) { [weak self] in self?.refresh() }
    }
}

// --------------------------------------------------------------------------- //
// Formatting helpers
// --------------------------------------------------------------------------- //
func fmtTokens(_ n: Int) -> String {
    let d = Double(n)
    if d >= 1e9 { return String(format: "%.2fB", d / 1e9) }
    if d >= 1e6 { return String(format: "%.1fM", d / 1e6) }
    if d >= 1e3 { return String(format: "%.1fK", d / 1e3) }
    return "\(n)"
}
func fmtCost(_ c: Double) -> String {
    c >= 100 ? String(format: "$%.0f", c) : String(format: "$%.2f", c)
}
func modelDisplay(_ id: String) -> String {
    let s = id.lowercased()
    if s.contains("opus")   { return "Opus" }
    if s.contains("sonnet") { return "Sonnet" }
    if s.contains("haiku")  { return "Haiku" }
    if s.contains("fable")  { return "Fable" }
    if id == "unknown" || id.isEmpty { return "Other" }
    return id
}
func modelColor(_ id: String) -> Color {
    let s = id.lowercased()
    if s.contains("opus")   { return .purple }
    if s.contains("sonnet") { return .blue }
    if s.contains("haiku")  { return .teal }
    if s.contains("fable")  { return .pink }
    return .gray
}
func agoString(sinceEpoch: Double) -> String {
    let secs = max(0, Date().timeIntervalSince1970 - sinceEpoch)
    if secs < 90 { return "\(Int(secs))s" }
    let mins = secs / 60
    if mins < 90 { return "\(Int(mins))m" }
    let hrs = mins / 60
    if hrs < 36 { return String(format: "%.1fh", hrs) }
    return "\(Int(hrs / 24))d"
}

// Keep-awake, in the user's language — named by the consequence, not the
// mechanism (the TUI card already reads this way). Shared by the popover row
// and the dashboard card so the two never drift.
enum KeepAwakeCopy {
    /// Compact title for the flat popover row.
    static func rowTitle(_ mode: String) -> String {
        switch mode {
        case "idle":      return "Staying awake · lid open"
        case "clamshell": return "Staying awake · lid closed"
        default:          return "Sleep allowed"
        }
    }
    /// Headline for the dashboard card.
    static func title(_ mode: String) -> String {
        switch mode {
        case "idle":      return "Staying awake"
        case "clamshell": return "On vigil · lid closed OK"
        default:          return "Sleep allowed"
        }
    }
    /// The consequence, one line.
    static func line(_ mode: String) -> String {
        switch mode {
        case "idle":      return "Long agents keep running while the lid is open."
        case "clamshell": return "Agents keep running even after you close the lid."
        default:          return "The Mac may sleep on its own — a long agent can be cut off."
        }
    }
    /// Menu / picker option labels, in mode order [off, idle, clamshell].
    static let options: [(mode: String, label: String)] = [
        ("off", "Sleep allowed"),
        ("idle", "Awake — lid open"),
        ("clamshell", "Awake — lid closed"),
    ]
}

// Country table (matches the TUI). Sorted by name for the picker.
let COUNTRIES: [(cc: String, name: String)] = [
    ("US", "United States"), ("CA", "Canada"), ("GB", "United Kingdom"),
    ("DE", "Germany"), ("FR", "France"), ("AU", "Australia"), ("JP", "Japan"),
    ("IN", "India"), ("SG", "Singapore"), ("NL", "Netherlands"),
    ("IE", "Ireland"), ("ES", "Spain"), ("IT", "Italy"), ("SE", "Sweden"),
    ("CH", "Switzerland"), ("BR", "Brazil"), ("MX", "Mexico"),
    ("KR", "South Korea"), ("AE", "UAE"), ("NO", "Norway"), ("FI", "Finland"),
    ("DK", "Denmark"), ("BE", "Belgium"), ("AT", "Austria"), ("PL", "Poland"),
    ("PT", "Portugal"), ("CZ", "Czechia"), ("NZ", "New Zealand"),
    ("ZA", "South Africa"), ("TR", "Türkiye"), ("IL", "Israel"),
    ("AR", "Argentina"), ("CL", "Chile"), ("HK", "Hong Kong"),
    ("TW", "Taiwan"), ("TH", "Thailand"), ("MY", "Malaysia"),
    ("ID", "Indonesia"), ("PH", "Philippines"), ("SA", "Saudi Arabia"),
    ("EG", "Egypt"), ("NG", "Nigeria"), ("UA", "Ukraine"),
].sorted { $0.name < $1.name }

// ISO country code → flag emoji (regional indicators).
func flag(_ cc: String?) -> String {
    guard let cc = cc, cc.count == 2 else { return "" }
    var out = ""
    for u in cc.uppercased().unicodeScalars {
        guard let s = UnicodeScalar(127397 + u.value) else { return "" }
        out.unicodeScalars.append(s)
    }
    return out
}
