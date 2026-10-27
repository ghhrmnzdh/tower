// Tower — the menu bar popover. Glanceable, Wi-Fi-menu flat: rows and
// dividers, no card chrome. Section order = attention order: header (guard),
// net weather, Needs You, collisions, Agents, resting, location, plan.
//
// Motion contract (DesignSystem.swift): a working agent's mark is alive,
// in-flight activity shimmers, done pops once and glows briefly, failure fades
// in sober, queue
// moves spring via matchedGeometryEffect. Reduce Motion degrades everything
// to quiet fades. At most one glowing row at a time (newest wins).

import AppKit
import SwiftUI

struct PopoverView: View {
    @ObservedObject var model: TowerModel
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    /// The embedding surface's visibility — only meaningful for the Settings
    /// preview, which lives in the dashboard. The real popover uses its own.
    @Environment(\.surfaceVisible) private var hostVisible
    @Namespace private var agentSpace
    /// Rendered small & inert inside Settings → Popover as a live preview: it
    /// drops the footer nav and the danger alerts (which must not double up with
    /// the real popover / dashboard) but shows the exact section composition.
    var isPreview = false

    // Popover composition — which sections show, in what order, and how tight.
    // Written by Settings → Popover (drag to reorder, switch to show), read
    // here; both sides share PopPref keys/defaults so they can never drift. The
    // header (guard) and footer stay put, and inside Agents the needs-you queue
    // keeps its rank — you order the sections, not what outranks what.
    @AppStorage(PopPref.net) private var showNet = true
    @AppStorage(PopPref.agents) private var showAgents = true
    @AppStorage(PopPref.location) private var showLocation = true
    @AppStorage(PopPref.keepawake) private var showKeepAwake = true
    @AppStorage(PopPref.apps) private var showApps = false
    @AppStorage(PopPref.plan) private var showPlan = true
    @AppStorage(PopPref.density) private var density = "comfy"
    @AppStorage(PopPref.order) private var order = PopPref.defaultOrder

    private var sections: [PopSection] {
        PopSection.order(order).filter { sec in
            switch sec {
            case .net: return showNet
            case .agents: return showAgents
            case .location: return showLocation
            case .apps: return showApps && model.hasClaudeApps
            case .keepawake: return showKeepAwake
            case .plan: return showPlan
            }
        }
    }

    var body: some View {
        VStack(spacing: 0) {
            PopHeader(model: model)
            if !model.alive {
                HStack(spacing: 8) {
                    ProgressView().controlSize(.small)
                    Text("Starting up…")
                        .font(TowerDesign.Font.activity).foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, alignment: .leading).padding(16)
            } else {
                // Cap the scrollable middle so the popover can never grow taller
                // than the screen — an oversized popover gets shoved off-anchor
                // and clipped by the menu bar. Header + footer stay pinned.
                //
                // .defaultScrollAnchor(.topLeading) is load-bearing, not
                // cosmetic: the middle reorders/resizes under an animation
                // (matchedGeometry, the reorder spring, or a section toggling on
                // and off). Mid-animation the column's height briefly overshoots
                // the 460 cap, which hands the ScrollView a transient scroll
                // range; without a pinned anchor it lands at a NON-zero content
                // offset and STICKS there after the content settles back under
                // the cap — the recurring "UI shifted out of view" bug (top rows
                // stranded above the fold). Anchoring top-leading forces the
                // resting position back to the origin on every content-size
                // change, on both axes, so no reflow — including a customization
                // toggle — can leave a stuck offset.
                ScrollView {
                    VStack(spacing: 0) {
                        // Dividers sit BETWEEN visible sections only (never a
                        // leading/trailing edge), so hiding a section never
                        // leaves an orphan rule. Order comes from `sections`.
                        ForEach(Array(sections.enumerated()), id: \.element) { idx, sec in
                            if idx > 0 {
                                Divider().padding(.horizontal, TowerDesign.Size.padH)
                            }
                            section(sec)
                                .towerRow()
                                .contextMenu { sectionMenu(sec) }
                        }
                    }
                    // Let the column TRACK THE VIEWPORT (maxWidth: .infinity)
                    // rather than assert a constant 360 width: content then
                    // equals the viewport by construction, so the ScrollView
                    // never has overflow to horizontally center (the old
                    // "AGENTS"→"GENTS" left-clip). Leading alignment fixes the
                    // origin; .clipped() trims transient per-row overflow.
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .clipped()
                    .animation(.tower(TowerDesign.Motion.settle, reduced: reduceMotion),
                               value: sections)
                }
                .frame(width: TowerDesign.Size.popoverWidth)
                .frame(maxHeight: 460)
                .clipped()
                .defaultScrollAnchor(.topLeading)
                .scrollBounceBehavior(.basedOnSize)
            }
            if !isPreview {
                Divider()
                PopFooter(model: model)
            }
        }
        .frame(width: TowerDesign.Size.popoverWidth)
        .environment(\.popoverCompact, density == "compact")
        .tint(TowerDesign.ink)
        .toggleStyle(.tower)
        .environment(\.surfaceVisible, isPreview ? hostVisible : model.popoverVisible)
        .animation(.tower(TowerDesign.Motion.settle, reduced: reduceMotion), value: model.alive)
        .modifier(ConditionalDanger(model: model, active: !isPreview))
    }

    /// Right-click any section: hide it right here, or open the composer.
    @ViewBuilder private func sectionMenu(_ sec: PopSection) -> some View {
        Button("Hide \(sec.title)") {
            withAnimation(.tower(TowerDesign.Motion.settle, reduced: reduceMotion)) {
                UserDefaults.standard.set(false, forKey: sec.visibilityKey)
            }
        }
        Button("Customize Popover…") {
            (NSApp.delegate as? AppDelegate)?.openDashboard(tab: .settings)
        }
    }

    // Order from `sections`; each case gated there. Keeping this a switch (not a
    // stored view list) preserves the per-section @ObservedObject wiring.
    @ViewBuilder private func section(_ sec: PopSection) -> some View {
        switch sec {
        case .net:       NetRow(model: model)
        case .agents:    AgentsSection(model: model, space: agentSpace)
        case .location:  LocationRow(model: model)
        case .apps:      ClaudeAppsSection(model: model)
        case .keepawake: KeepAwakeRow(model: model)
        case .plan:      PlanSection(model: model)
        }
    }
}

// Attach the two-stage danger alerts only on the real popover — never on the
// inert Settings preview, where a second copy bound to the same model would
// fight the dashboard's own alerts.
private struct ConditionalDanger: ViewModifier {
    let model: TowerModel
    let active: Bool
    func body(content: Content) -> some View {
        if active { content.dangerAlerts(model) } else { content }
    }
}

// --------------------------------------------------------------------------- //
// Header — guard status + the one primary control (route toggle).
// --------------------------------------------------------------------------- //
struct PopHeader: View {
    @ObservedObject var model: TowerModel
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    var body: some View {
        let st = model.status
        let routed = model.state?.routing?.installed ?? false
        let pending = model.retryPending
        // A status card, not a title bar: the radar is the state, the verdict
        // names it, the sub-line says where (or that Claude is reconnecting).
        // Only a hold or danger tints the card — the quiet state is quiet.
        let wash: Color? = (st == .protected || st == .monitor || st == .starting)
            ? nil : st.swiftUIColor
        HStack(spacing: 12) {
            TowerRadar(state: model.radarState, size: 36, color: .primary,
                       awake: model.awakeGlow)
                .frame(width: 36, height: 36)
            VStack(alignment: .leading, spacing: 2) {
                Text(st.title)
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(st == .protected ? AnyShapeStyle(.primary)
                                                      : AnyShapeStyle(st.swiftUIColor))
                    .lineLimit(1)
                    .contentTransition(.opacity)
                // While a Claude request is held/retrying, the sub-line shimmers
                // "Reconnecting Claude…" — an agentic pending state, not a
                // failure. It clears the moment the guard passes and Claude
                // resumes on its own. Reduce Motion falls back to a static line.
                if pending {
                    Text("Reconnecting Claude…")
                        .font(TowerDesign.Font.activity)
                        .foregroundStyle(st.swiftUIColor)
                        .shimmer(!reduceMotion)
                        .transition(.opacity)
                } else {
                    HStack(spacing: 5) {
                        if st == .protected {
                            Circle().fill(Color(nsColor: .systemGreen)).frame(width: 6, height: 6)
                        }
                        Text(headerLine(st))
                            .lineLimit(1)
                            .contentTransition(.opacity)
                    }
                    .font(TowerDesign.Font.activity)
                    .foregroundStyle(.secondary)
                }
            }
            Spacer(minLength: 8)
            Toggle("", isOn: Binding(get: { routed }, set: { model.setRouting($0) }))
                .labelsHidden().toggleStyle(.tower).controlSize(.small)
                .help("Route Claude through the guard")
        }
        .padding(.horizontal, 12).padding(.vertical, 10)
        .background {
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .fill(wash.map { $0.opacity(0.12) } ?? Color.primary.opacity(0.045))
                .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .strokeBorder(Color.primary.opacity(0.06), lineWidth: 0.5))
        }
        .padding(.horizontal, 8).padding(.top, 8).padding(.bottom, 4)
        .animation(.tower(TowerDesign.Motion.settle, reduced: reduceMotion), value: st.title)
    }

    private func headerLine(_ st: GuardStatus) -> String {
        switch st {
        case .protected: return "Fenced to \(flag(model.targetCC)) \(model.targetName) · path open"
        case .blocking:  return "Outside \(model.targetName) — Claude is held, not failed"
        case .unstable:  return "No usable path — requests held, resume on their own"
        case .locating:  return "Confirming your location…"
        case .unrouted:  return "Claude connects directly — no guard"
        case .monitor:   return "Watching only — enforcement is off"
        case .starting:  return "Starting the guard…"
        }
    }
}

// --------------------------------------------------------------------------- //
// Net weather — one quiet line when fine, a verdict banner when not.
// The banner wording is the product: instant fault isolation.
// --------------------------------------------------------------------------- //
struct NetRow: View {
    @ObservedObject var model: TowerModel
    var body: some View {
        let net = model.state?.net
        switch model.netStatus {
        case .online:
            // The weather strip: two readings, nothing more — the history
            // lives on the dashboard's Network page.
            HStack(spacing: 14) {
                reading("Internet", net?.internet_ms, symbol: "network")
                reading("API", net?.api_ms, symbol: "server.rack")
                Spacer(minLength: 6)
            }
            .padding(.horizontal, TowerDesign.Size.padH)
            .padding(.vertical, 7)
        case .degraded:
            switch net?.reason {
            case "dns":
                banner(icon: "wifi.exclamationmark", color: .orange,
                       title: "DNS problem",
                       sub: "Your resolver is failing — not Anthropic")
            case "api_slow":
                // Link is fine; only the path to Anthropic is slow. Show the
                // handshake time (not the spoofable local ping) and don't cry
                // "timeout" — degraded still lets traffic through.
                banner(icon: "clock.badge.exclamationmark", color: .orange,
                       title: "Slow path to Anthropic",
                       sub: "handshake \(fmtMs(net?.api_ms)) — link is fine, replies may lag")
            default:   // "link_slow" or a generic degraded (e.g. NAT64)
                banner(icon: "wifi.exclamationmark", color: .orange,
                       title: "Internet is slow",
                       sub: "ping \(fmtMs(net?.internet_ms)) — expect Claude timeouts")
            }
        case .offline:
            banner(icon: "wifi.slash", color: .red,
                   title: "Your internet is offline",
                   sub: "Claude errors are local — not Anthropic")
        case .apiIssue:
            banner(icon: "exclamationmark.icloud", color: .orange,
                   title: "Anthropic API unreachable",
                   sub: "Your internet is fine (\(fmtMs(net?.internet_ms)))")
        case .captive:
            banner(icon: "wifi.exclamationmark", color: .red,
                   title: "Wi-Fi login required",
                   sub: "Open a browser to sign in to this network")
        case .checking, .unknown:
            EmptyView()   // old daemon or first sample — say nothing alarming
        }
    }

    func reading(_ label: String, _ ms: Double?, symbol: String) -> some View {
        HStack(spacing: 5) {
            Image(systemName: symbol).font(.system(size: 10, weight: .medium))
                .foregroundStyle(.tertiary)
            Text(label).font(.system(size: 11)).foregroundStyle(.secondary)
            Text(ms.map { "\(Int($0))" } ?? "—")
                .font(.system(size: 12, weight: .semibold, design: .rounded)).monospacedDigit()
            + Text(" ms").font(.system(size: 10)).foregroundStyle(.tertiary)
        }
    }

    func banner(icon: String, color: Color, title: String, sub: String) -> some View {
        HStack(spacing: 8) {
            Image(systemName: icon).font(.system(size: 13, weight: .semibold))
                .foregroundStyle(color)
            VStack(alignment: .leading, spacing: 1) {
                Text(title).font(.system(size: 12, weight: .semibold))
                Text(sub).font(.system(size: 10)).foregroundStyle(.secondary)
            }
            Spacer()
        }
        .padding(8)
        .background(color.opacity(0.14),
                    in: RoundedRectangle(cornerRadius: 8, style: .continuous))
        .padding(.horizontal, 10)
        .padding(.vertical, 5)
        .transition(.opacity)
    }
}

func fmtMs(_ v: Double?) -> String {
    guard let v = v else { return "—" }
    return "\(Int(v)) ms"
}

// --------------------------------------------------------------------------- //
// The agents block: summary line → Needs You → collisions → working agents →
// resting. The dopamine layer lives here.
// --------------------------------------------------------------------------- //
struct AgentsSection: View {
    @ObservedObject var model: TowerModel
    var space: Namespace.ID
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var showResting = false
    @AppStorage(PopPref.resting) private var restingVisible = true

    var body: some View {
        let needs = model.needsYou
        let working = model.workingAgents
        let resting = model.resting
        let summaryInfo = model.state?.agents?.summary
        let hasAgentsKey = model.state?.agents != nil

        VStack(alignment: .leading, spacing: 0) {
            if hasAgentsKey {
                // Summary — the ambient momentum line. Counters tick.
                HStack(spacing: 4) {
                    Text("AGENTS").font(TowerDesign.Font.caption.weight(.heavy))
                        .tracking(0.7).foregroundStyle(.secondary)
                        .fixedSize(horizontal: true, vertical: false)
                        // Keep this static label out of the list's reorder
                        // animation — animating a `.tracking` Text clips its
                        // leading glyph ("AGENTS" → "GENTS"). The summary
                        // counter beside it keeps its own numericText tick.
                        .transaction { $0.animation = nil }
                    Spacer()
                    summaryLine(summaryInfo)
                }
                .padding(.horizontal, TowerDesign.Size.padH)
                .padding(.top, 8).padding(.bottom, 4)

                ForEach(needs) { s in
                    NeedsYouRow(model: model, session: s)
                        .matchedGeometryEffect(id: s.id, in: space)
                        .towerRow()
                }

                // Static, motionless callout: chats started before the guard are
                // unprotected until restarted. Never pulses — needs-you stays the
                // loudest thing. The reverse (pinned) case is a quiet hint only.
                if model.unguardedCount > 0 {
                    GuardGapBanner(model: model, count: model.unguardedCount, unguarded: true)
                } else if model.pinnedCount > 0 {
                    GuardGapBanner(model: model, count: model.pinnedCount, unguarded: false)
                }

                ForEach(model.collisions) { c in
                    CollisionBanner(collision: c).towerRow()
                }

                ForEach(working) { s in
                    AgentRow(model: model, session: s)
                        .matchedGeometryEffect(id: s.id, in: space)
                        .towerRow()
                }

                if needs.isEmpty && working.isEmpty {
                    EmptyState(anyResting: restingVisible && !resting.isEmpty)
                }

                if restingVisible && !resting.isEmpty {
                    DisclosureGroup(isExpanded: $showResting) {
                        ForEach(resting) { s in RestingRow(session: s).towerRow() }
                    } label: {
                        Text("Resting · \(resting.count)")
                            .font(TowerDesign.Font.activity).foregroundStyle(.tertiary)
                    }
                    .padding(.horizontal, TowerDesign.Size.padH)
                    .padding(.vertical, 4)
                }
            } else {
                EmptyState(anyResting: false)   // old daemon: quiet, charming
            }
        }
        .animation(.tower(TowerDesign.Motion.reorder, reduced: reduceMotion),
                   value: needs.map { $0.id + ($0.status ?? "") } + ["|"]
                        + working.map(\.id) + ["|"] + resting.map(\.id)
                        + model.collisions.map(\.id) + ["\(showResting)"])
    }

    /// Only what actually needs you is called "needs you"; a finished turn is
    /// "your turn" — listed, but never counted as an interruption. Numbers in
    /// ink, their words quiet: "1 working · 2 done today".
    func summaryLine(_ h: GAgentSummary?) -> some View {
        SummaryCounts(items: [
            (model.urgentCount, "hand.raised.fill", "need you", Color(nsColor: .systemOrange)),
            (h?.working ?? 0, "waveform", "working", .primary),
            (model.yourTurnCount, "arrowshape.turn.up.left.fill", "your turn", .primary),
            (h?.done_today ?? 0, "checkmark.circle.fill", "done today", .secondary),
        ])
    }
}

// A needs-you row: distinct symbol shape + color + position per state.
// Done pops and glows once; failure arrives sober. Click = focus.
struct NeedsYouRow: View {
    @ObservedObject var model: TowerModel
    let session: GAgentSession
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var glow = false
    @State private var hovering = false

    var body: some View {
        let st = AgentStatus(raw: session.status)
        HStack(spacing: 9) {
            if st == .done || st == .waitingInput {
                DoneCheck()
            } else {
                Image(systemName: st.symbol)
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(st.color)
                    .frame(width: 22)
                    .transition(.opacity)   // sober: no bounce for bad news
            }
            VStack(alignment: .leading, spacing: 1) {
                HStack(spacing: 6) {
                    Text(session.project_name ?? "agent")
                        .font(TowerDesign.Font.rowTitle.weight(.medium))
                        .foregroundStyle(.primary)      // the name: one color
                        .lineLimit(1)
                    ModelMeta(session: session)
                    UnguardedChip(model: model, session: session)
                }
                Text(rowSubtitle(session, st))
                    .font(TowerDesign.Font.activity)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
            Spacer()
            if hovering {
                Button("Dismiss") {
                    model.send(["cmd": "dismiss", "session_id": session.id])
                }
                .buttonStyle(.borderless).controlSize(.small)
                .font(TowerDesign.Font.caption)
            }
            Text(agoString(sinceEpoch: session.status_since ?? Date().timeIntervalSince1970))
                .font(TowerDesign.Font.counter).foregroundStyle(.tertiary)
        }
        .padding(.horizontal, TowerDesign.Size.padH)
        .padding(.vertical, TowerDesign.Size.rowVPad)
        .background((glow ? st.color.opacity(0.12) : Color.clear))
        .contentShape(Rectangle())
        .onHover { hovering = $0 }
        .onTapGesture { focus() }
        .onAppear {
            guard (st == .done || st == .waitingInput), !reduceMotion else { return }
            glow = true
            withAnimation(.easeOut(duration: 0.4).delay(TowerDesign.Motion.glowHold)) {
                glow = false
            }
        }
    }

    func rowSubtitle(_ s: GAgentSession, _ st: AgentStatus) -> String {
        // A failed agent carries the *reason* in `activity` (e.g. "API error —
        // retrying 3/10" or "API Error: Connection closed"). Surface that
        // instead of the generic "failed · <old prompt>" — the reason is the
        // whole point of the alert.
        if st == .failed, let a = s.activity, !a.isEmpty {
            return a
        }
        // A finished turn: show what the agent produced (its final line), not
        // the prompt the user typed. Falls back to title/prompt when the daemon
        // didn't capture a result (old daemon, or a no-text turn).
        if st == .done || st == .waitingInput, let r = s.result, !r.isEmpty {
            return st.phrase + " · " + r
        }
        var out = st.phrase
        if let t = s.title ?? s.last_prompt, !t.isEmpty {
            out += " · \(t)"
        }
        return out
    }

    /// A click shows that agent's terminal — the one thing a row does.
    func focus() {
        if session.focusable == true {
            model.send(["cmd": "focus", "session_id": session.id])
        }
    }
}

// The payoff: a checkmark that draws itself on once. ~0.6s, then quiet.
struct DoneCheck: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var drawn = false
    var body: some View {
        ZStack {
            Circle()
                .stroke(Color(nsColor: .systemGreen), lineWidth: 1.5)
                .opacity(drawn ? 1 : 0)
            CheckShape()
                .trim(from: 0, to: drawn ? 1 : 0)
                .stroke(Color(nsColor: .systemGreen),
                        style: StrokeStyle(lineWidth: 2, lineCap: .round, lineJoin: .round))
        }
        .frame(width: 16, height: 16)
        .frame(width: 22)
        .onAppear {
            if reduceMotion { drawn = true; return }
            withAnimation(TowerDesign.Motion.payoff.delay(0.05)) { drawn = true }
        }
    }
}

struct CheckShape: Shape {
    func path(in rect: CGRect) -> Path {
        var p = Path()
        p.move(to: CGPoint(x: rect.width * 0.26, y: rect.height * 0.54))
        p.addLine(to: CGPoint(x: rect.width * 0.44, y: rect.height * 0.72))
        p.addLine(to: CGPoint(x: rect.width * 0.76, y: rect.height * 0.32))
        return p
    }
}

// The model + effort chip: a single neutral capsule carrying the model name and
// — when known — the reasoning effort in its own compartment. Deliberately
// colorless (the model's color lives in its living mark, not here) and set in
// JetBrains Mono so the version and effort read as precise, technical tokens.
// Two-tone by opacity, hairline-bordered. Effort compartment omitted when unknown.
struct ModelBadge: View {
    let session: GAgentSession
    var body: some View {
        HStack(spacing: 0) {
            Text(session.modelDisplay)
                .font(TowerDesign.Font.mono(9.5))
                .padding(.leading, 6)
                .padding(.trailing, session.effortLabel == nil ? 6 : 5)
                .padding(.vertical, 2)
            if let e = session.effortLabel {
                Text(e)
                    .font(TowerDesign.Font.mono(8.5, bold: true))
                    .tracking(0.4)
                    .padding(.horizontal, 5)
                    .padding(.vertical, 2)
                    .background(Color.primary.opacity(0.07))
                    .overlay(Rectangle().frame(width: 0.6)   // compartment divider
                        .foregroundStyle(Color.primary.opacity(0.14)), alignment: .leading)
            }
        }
        .foregroundStyle(.secondary)
        .background(Color.primary.opacity(0.05))
        .clipShape(Capsule(style: .continuous))
        .overlay(Capsule(style: .continuous)
            .strokeBorder(Color.primary.opacity(0.12), lineWidth: 0.6))
        .fixedSize()
        .help("\(session.modelDisplay)"
              + (session.effortLabel.map { " · \($0.lowercased()) effort" } ?? ""))
    }
}

// A dim capsule marking a session that started before the guard: its requests go
// out DIRECT until it's restarted. Shown only when routing is on and this session
// is definitely unguarded (never on unknown — we don't alarm on uncertainty).
struct UnguardedChip: View {
    @ObservedObject var model: TowerModel
    let session: GAgentSession
    var body: some View {
        if model.routingIntended && session.guarded == false {
            Text("unguarded")
                .font(TowerDesign.Font.mono(8.5, bold: true))
                .tracking(0.3)
                .padding(.horizontal, 5).padding(.vertical, 2)
                .foregroundStyle(Color(nsColor: .systemOrange))
                .background(Color.orange.opacity(0.12))
                .clipShape(Capsule(style: .continuous))
                .help("This chat started before the guard — restart it to route "
                      + "it through Tower.")
        }
    }
}

// A working row, Mail-style: the model's living mark, the project with its
// model in quiet text, the live activity line (shimmering only while a tool
// call is in flight); on the right the turn's running clock over its tool
// count. No pills, no borders — type weight and gray levels carry the order.
struct AgentRow: View {
    @ObservedObject var model: TowerModel
    let session: GAgentSession
    @AppStorage(PopPref.subagents) private var showSubagents = true
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.surfaceVisible) private var visible
    @State private var hovering = false

    var body: some View {
        let tier = ModelTier(family: session.model_family)
        let tooling = session.pending_tool != nil
        let subs = session.subagentsOrdered
        let tools = session.ticks?.tools_done ?? 0
        VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .center, spacing: 10) {
                ModelGlyphView(tier: tier, working: true)
                VStack(alignment: .leading, spacing: 2) {
                    HStack(alignment: .firstTextBaseline, spacing: 7) {
                        Text(session.project_name ?? "agent")
                            .font(.system(size: 13, weight: .semibold))
                            .lineLimit(1)
                            .layoutPriority(1)
                        ModelMeta(session: session)
                        UnguardedChip(model: model, session: session)
                        if session.health?.level == "warn" {
                            Image(systemName: "exclamationmark.triangle.fill")
                                .font(.system(size: 9))
                                .foregroundStyle(Color(nsColor: .systemYellow))
                                .help((session.health?.reasons ?? []).joined(separator: "\n"))
                        }
                        Spacer(minLength: 6)
                        Text(clock)
                            .font(.system(size: 11, weight: .medium)).monospacedDigit()
                            .foregroundStyle(.secondary)
                            .fixedSize()
                            .help(session.turn_at != nil ? "This turn has run \(clock)"
                                  : "Last activity \(clock) ago")
                    }
                    HStack(alignment: .firstTextBaseline, spacing: 5) {
                        if tooling && visible {     // a spinner animates even off screen
                            ProgressView().controlSize(.mini).frame(width: 10, height: 10)
                        }
                        Text(session.activity ?? "thinking…")
                            .font(TowerDesign.Font.activity)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                            .shimmer(tooling && !reduceMotion)
                        Spacer(minLength: 6)
                        if tools > 0 {
                            Text("\(tools) tool\(tools == 1 ? "" : "s")")
                                .font(TowerDesign.Font.counter)
                                .foregroundStyle(.tertiary)
                                .contentTransition(.numericText())
                                .fixedSize()
                        }
                    }
                }
            }
            if showSubagents && !subs.isEmpty {
                SubagentTree(subagents: subs, limit: 3).towerRow()
            }
        }
        .animation(.tower(TowerDesign.Motion.settle, reduced: reduceMotion),
                   value: subs.map(\.id))
        .padding(.horizontal, TowerDesign.Size.padH)
        .padding(.vertical, TowerDesign.Size.rowVPad + 1)
        .background(
            RoundedRectangle(cornerRadius: 9, style: .continuous)
                .fill(Color.primary.opacity(hovering ? 0.05 : 0))
                .padding(.horizontal, 6)
        )
        .contentShape(Rectangle())
        .onHover { h in
            withAnimation(.easeOut(duration: 0.15)) { hovering = h }
        }
        .onTapGesture {
            if session.focusable == true {
                model.send(["cmd": "focus", "session_id": session.id])
            }
        }
        .help(session.focusable == true ? "Show this agent's terminal" : "")
    }

    /// The turn's own clock when the daemon knows when it began; otherwise how
    /// fresh the last sign of life is.
    private var clock: String {
        if let t = session.turn_at { return elapsedString(sinceEpoch: t) }
        return agoString(sinceEpoch: session.last_activity ?? Date().timeIntervalSince1970)
    }
}

/// The model as quiet text — "Opus 5.5 · High" — beside the project name. The
/// model's color lives in its living mark; here it's just a fact.
struct ModelMeta: View {
    let session: GAgentSession
    var body: some View {
        Text(session.modelDisplay + (session.effortLabel.map { " · " + $0.capitalized } ?? ""))
            .font(.system(size: 11))
            .foregroundStyle(.tertiary)
            .lineLimit(1)
            .truncationMode(.tail)
            .help("\(session.modelDisplay)"
                  + (session.effortLabel.map { " · \($0.lowercased()) effort" } ?? ""))
    }
}

struct RestingRow: View {
    let session: GAgentSession
    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "zzz").font(.system(size: 10))
                .foregroundStyle(.tertiary).frame(width: 22)
            Text(session.project_name ?? "agent")
                .font(TowerDesign.Font.activity).foregroundStyle(.tertiary)
            Spacer()
            Text(agoString(sinceEpoch: session.last_activity ?? 0))
                .font(TowerDesign.Font.counter).foregroundStyle(.quaternary)
        }
        .padding(.vertical, 3)
    }
}

// Guard-coverage callout. unguarded=true: chats that started before the guard and
// send DIRECT requests until restarted (amber, actionable). unguarded=false: chats
// still guarded by a proxy the user turned off — safe until restarted (a quiet,
// reassuring tertiary hint, not an alarm).
struct GuardGapBanner: View {
    @ObservedObject var model: TowerModel
    let count: Int
    let unguarded: Bool
    var body: some View {
        let plural = count == 1 ? "" : "s"
        if unguarded {
            VStack(alignment: .leading, spacing: 5) {
                HStack(spacing: 8) {
                    Image(systemName: "shield.slash")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(Color(nsColor: .systemOrange))
                    Text("\(count) chat\(plural) started before the guard — restart to protect")
                        .font(.system(size: 11, weight: .medium))
                    Spacer(minLength: 0)
                }
                // Name each one and make it the jump target — these chats are
                // usually idle, so their rows sit folded under "Resting".
                ForEach(model.unguardedSessions.prefix(3)) { s in
                    UnguardedChatLink(model: model, session: s)
                }
            }
            .padding(7)
            .background(Color.orange.opacity(0.12),
                        in: RoundedRectangle(cornerRadius: 8, style: .continuous))
            .padding(.horizontal, 10)
            .padding(.vertical, 3)
            .transition(.opacity)
        } else {
            HStack(spacing: 6) {
                Image(systemName: "shield.lefthalf.filled")
                    .font(.system(size: 10))
                Text("\(count) chat\(plural) still guarded by the previous routing — protected until restarted")
                    .font(.system(size: 10))
                Spacer()
            }
            .foregroundStyle(.tertiary)
            .padding(.horizontal, 10)
            .padding(.vertical, 2)
            .transition(.opacity)
        }
    }
}

/// One unguarded chat inside the banner: its project and terminal, and a click
/// that brings that terminal forward.
struct UnguardedChatLink: View {
    @ObservedObject var model: TowerModel
    let session: GAgentSession
    @State private var hovering = false
    var body: some View {
        Button {
            if session.focusable == true {
                model.send(["cmd": "focus", "session_id": session.id])
            }
        } label: {
            HStack(spacing: 6) {
                Text(session.project_name ?? "chat")
                    .font(.system(size: 11, weight: .medium))
                if let tty = session.tty {
                    Text(tty).font(TowerDesign.Font.mono(9)).foregroundStyle(.tertiary)
                }
                Spacer(minLength: 4)
                Text(session.focusable == true ? "Show" : "Restart it")
                    .font(.system(size: 10, weight: .medium))
                if session.focusable == true {
                    Image(systemName: "chevron.right").font(.system(size: 8, weight: .semibold))
                }
            }
            .foregroundStyle(hovering ? AnyShapeStyle(.primary) : AnyShapeStyle(.secondary))
            .padding(.horizontal, 6).padding(.vertical, 3)
            .background(Color.primary.opacity(hovering ? 0.08 : 0.04),
                        in: RoundedRectangle(cornerRadius: 6, style: .continuous))
            .padding(.leading, 20)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { hovering = $0 }
        .disabled(session.focusable != true)
        .help(session.focusable == true ? "Bring this chat's terminal forward"
              : "Restart this chat to route it through Tower")
    }
}

struct CollisionBanner: View {
    let collision: GCollision
    var body: some View {
        let fileLevel = collision.level == "file"
        let repo = (collision.git_root as NSString?)?.lastPathComponent ?? "repo"
        let n = collision.session_ids?.count ?? 2
        HStack(spacing: 8) {
            Image(systemName: "arrow.triangle.merge")
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(fileLevel ? Color(nsColor: .systemRed)
                                           : Color(nsColor: .systemYellow))
            Text(fileLevel
                 ? "\(n) agents editing \((collision.files?.first as NSString?)?.lastPathComponent ?? "the same file") in \(repo)"
                 : "\(n) agents in \(repo)")
                .font(.system(size: 11, weight: .medium))
            Spacer()
        }
        .padding(7)
        .background((fileLevel ? Color.red : Color.yellow).opacity(0.12),
                    in: RoundedRectangle(cornerRadius: 8, style: .continuous))
        .padding(.horizontal, 10)
        .padding(.vertical, 3)
        .transition(.move(edge: .top).combined(with: .opacity))
    }
}

// No agents — a quiet, still scope.
struct EmptyState: View {
    var anyResting: Bool
    var body: some View {
        VStack(spacing: 6) {
            TowerRadar(state: .clear, size: 30, color: .secondary, animated: false)
                .frame(width: 30, height: 30)
                .opacity(0.6)
            Text("No agents running.")
                .font(TowerDesign.Font.activity).foregroundStyle(.secondary)
            Text("Run `claude` in any terminal and it'll show up here.")
                .font(TowerDesign.Font.caption).foregroundStyle(.tertiary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 14)
    }
}

// --------------------------------------------------------------------------- //
// Location — where the fence thinks you are.
// --------------------------------------------------------------------------- //
struct LocationRow: View {
    @ObservedObject var model: TowerModel
    @Environment(\.popoverCompact) private var compact
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @AppStorage(PopPref.ip) private var showIP = true
    @State private var spin = 0.0

    var body: some View {
        let loc = model.state?.location
        let target = model.targetCC
        let ok = loc?.status == "OK"
        let inTarget = loc?.in_target ?? false
        let offline = model.netStatus == .offline
        HStack(spacing: 11) {
            // The flag as a tile — the same footprint as every other row's mark.
            RoundedRectangle(cornerRadius: 7, style: .continuous)
                .fill(Color.primary.opacity(0.06))
                .overlay(Text(flag(ok ? loc?.country_cc : target)).font(.system(size: 15)))
                .overlay(alignment: .bottomTrailing) {
                    if ok && !offline {
                        Image(systemName: inTarget ? "checkmark.circle.fill" : "exclamationmark.circle.fill")
                            .font(.system(size: 10, weight: .bold))
                            .symbolRenderingMode(.palette)
                            .foregroundStyle(.white, inTarget ? Color(nsColor: .systemGreen)
                                                              : Color(nsColor: .systemOrange))
                            .offset(x: 3, y: 3)
                    }
                }
                .frame(width: 26, height: 26)
            VStack(alignment: .leading, spacing: 1) {
                Group {
                    if offline {
                        Text("Location unknown")
                    } else if ok {
                        Text([loc?.city, loc?.region].compactMap { $0 }.joined(separator: ", "))
                    } else {
                        Text("Locating…")
                    }
                }
                .font(TowerDesign.Font.rowTitle.weight(.medium))
                .lineLimit(1)
                if !compact {
                    Group {
                        if offline {
                            Text("Internet down — Claude is held until it's back")
                        } else if ok {
                            Text(inTarget ? "Inside \(model.targetName)"
                                          : "Outside \(model.targetName) — Claude is held")
                                .foregroundStyle(inTarget ? AnyShapeStyle(.secondary)
                                                          : AnyShapeStyle(Color(nsColor: .systemOrange)))
                            + Text(loc?.isp.map { "  ·  \($0)" } ?? "").foregroundStyle(.tertiary)
                        } else {
                            Text("Claude is held until your location is confirmed")
                        }
                    }
                    .font(TowerDesign.Font.activity)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                }
            }
            Spacer(minLength: 8)
            if showIP, ok, let ip = loc?.ip, !compact {
                Text(ip).font(TowerDesign.Font.mono(9.5)).foregroundStyle(.tertiary)
                    .lineLimit(1).textSelection(.enabled)
            }
            Button {
                model.send(["cmd": "recheck"])
                guard !reduceMotion else { return }
                withAnimation(.spring(response: 0.6, dampingFraction: 0.8)) { spin += 360 }
            } label: {
                Image(systemName: "arrow.clockwise")
                    .font(.system(size: 10, weight: .semibold))
                    .rotationEffect(.degrees(spin))
                    .frame(width: 22, height: 22)
                    .background(Circle().fill(Color.primary.opacity(0.06)))
                    .contentShape(Circle())
            }
            .buttonStyle(.plain)
            .foregroundStyle(.secondary)
            .help("Re-check location now")
        }
        .padding(.horizontal, TowerDesign.Size.padH)
        .padding(.vertical, compact ? 5 : 7)
    }
}

// --------------------------------------------------------------------------- //
// Claude apps — the same fence, for Claude Desktop (its chats AND the Claude
// Code it runs) and for claude.ai in a guarded Chrome-family window. Off by
// default (Settings adds it): Tower sees no live activity from either, so this
// is a launcher with an honest status line, not a monitor. Desktop running
// unguarded is the one amber state — a gap, never a failure — and closing it
// quits the user's app, so that action says "Relaunch" out loud.
// --------------------------------------------------------------------------- //
struct ClaudeAppsSection: View {
    @ObservedObject var model: TowerModel
    var body: some View {
        let apps = model.state?.apps
        // The row's ✕ hides the whole section; Settings brings it back.
        let hide = {
            withAnimation(TowerDesign.Motion.settle) {
                UserDefaults.standard.set(false, forKey: PopPref.apps)
            }
        }
        VStack(spacing: 0) {
            if let d = apps?.desktop, d.installed == true {
                let gap = d.running == true && d.guarded != true
                ClaudeAppRow(
                    icon: .app(ClaudeLaunch.desktopApp),
                    title: "Claude Desktop",
                    line: ClaudeLaunch.desktopLine(d),
                    warn: gap,
                    action: ClaudeLaunch.desktopAction(d),
                    help: gap ? "Quit Claude Desktop and reopen it through Tower"
                        : "Open Claude Desktop through the guard",
                    onHide: hide
                ) { ClaudeLaunch.desktop(model) }
            }
            if let w = apps?.web, w.available == true {
                ClaudeAppRow(
                    icon: .app(ClaudeLaunch.browserApp(w)),
                    title: "Claude on the web",
                    line: ClaudeLaunch.webLine(w),
                    warn: false,
                    action: "Open",
                    help: "claude.ai in its own guarded \(w.browser ?? "Chrome") window — sign in once there",
                    onHide: hide
                ) { ClaudeLaunch.web(model) }
            }
        }
    }
}

/// One place for what the launchers say and do — the popover rows and the
/// dashboard's toolbar menu read the same words.
enum ClaudeLaunch {
    static let desktopApp = "/Applications/Claude.app"
    static func browserApp(_ w: GApps.Web) -> String {
        "/Applications/\(w.browser ?? "Google Chrome").app"
    }
    static func desktopLine(_ d: GApps.Desktop) -> String {
        if d.running != true { return "Chats + Claude Code, through the guard" }
        return d.guarded == true ? "Guarded — its chats and Claude Code go through Tower"
                                 : "Unguarded — its chats and Claude Code go direct"
    }
    static func desktopAction(_ d: GApps.Desktop) -> String {
        if d.running != true { return "Open" }
        return d.guarded == true ? "Show" : "Relaunch guarded"
    }
    static func webLine(_ w: GApps.Web) -> String {
        w.running == true ? "Guarded \(w.browser ?? "Chrome") window open"
                          : "claude.ai in a guarded \(w.browser ?? "Chrome") window"
    }
    /// Relaunching quits the user's own Desktop, so only an unguarded running
    /// Desktop asks for it — and it is always this explicit click.
    static func desktop(_ model: TowerModel) {
        let d = model.state?.apps?.desktop
        model.send(["cmd": "desktop",
                    "relaunch": d?.running == true && d?.guarded != true])
    }
    static func web(_ model: TowerModel) { model.send(["cmd": "web"]) }
}

struct ClaudeAppRow: View {
    enum Icon { case app(String), symbol(String) }
    let icon: Icon
    let title: String
    let line: String
    let warn: Bool
    let action: String?
    let help: String
    var onHide: (() -> Void)? = nil
    let perform: () -> Void
    @Environment(\.popoverCompact) private var compact
    @State private var hovering = false
    @State private var rowHover = false

    var body: some View {
        HStack(spacing: 11) {
            iconView.frame(width: 26, height: 26)
            VStack(alignment: .leading, spacing: 1) {
                Text(title)
                    .font(TowerDesign.Font.rowTitle.weight(.medium))
                if !compact {
                    Text(line)
                        .font(TowerDesign.Font.activity)
                        .foregroundStyle(warn ? AnyShapeStyle(Color(nsColor: .systemOrange))
                                              : AnyShapeStyle(.secondary))
                        .lineLimit(1)
                        .contentTransition(.opacity)
                }
            }
            Spacer(minLength: 8)
            if let action {
                Button(action: perform) {
                    Text(action)
                        .font(.system(size: 11, weight: .medium))
                        .foregroundStyle(warn ? Color(nsColor: .systemOrange) : Color.primary)
                        .padding(.horizontal, 10).frame(height: 22)
                        .background(Capsule(style: .continuous).fill(
                            warn ? Color.orange.opacity(hovering ? 0.26 : 0.17)
                                 : Color.primary.opacity(hovering ? 0.13 : 0.07)))
                        .contentShape(Capsule())
                }
                .buttonStyle(.plain)
                .onHover { hovering = $0 }
                .help(help)
            }
            if let onHide, rowHover {
                Button(action: onHide) {
                    Image(systemName: "xmark")
                        .font(.system(size: 8, weight: .bold))
                        .foregroundStyle(.secondary)
                        .frame(width: 18, height: 18)
                        .background(Circle().fill(Color.primary.opacity(0.08)))
                        .contentShape(Circle())
                }
                .buttonStyle(.plain)
                .help("Hide from the popover — bring it back in Settings")
                .transition(.opacity.combined(with: .scale(scale: 0.8)))
            }
        }
        .padding(.horizontal, TowerDesign.Size.padH)
        .padding(.vertical, compact ? 5 : 7)
        .contentShape(Rectangle())
        .onHover { h in withAnimation(.easeOut(duration: 0.15)) { rowHover = h } }
    }

    @ViewBuilder private var iconView: some View {
        switch icon {
        case .app(let path):
            Image(nsImage: NSWorkspace.shared.icon(forFile: path))
                .resizable().interpolation(.high)
        case .symbol(let name):
            RoundedRectangle(cornerRadius: 7, style: .continuous)
                .fill(Color.primary.opacity(0.07))
                .overlay(Image(systemName: name)
                    .font(.system(size: 13, weight: .medium))
                    .foregroundStyle(.secondary))
        }
    }
}

// --------------------------------------------------------------------------- //
// Keep awake — the tower's lamp, as a row. The beacon mirrors the radar's core,
// so the same glow means the same thing everywhere; the title + line say what
// the policy is doing right now (holding / armed / off); the inline mode switch
// is one tap — a thumb that slides, no menu to open.
// --------------------------------------------------------------------------- //
struct KeepAwakeRow: View {
    @ObservedObject var model: TowerModel
    @Environment(\.popoverCompact) private var compact
    var body: some View {
        HStack(spacing: 11) {
            BeaconView(mode: model.awakeGlow, size: 26)
                .frame(width: 26, height: 26)
            VStack(alignment: .leading, spacing: 1) {
                Text(model.keepAwakeTitle)
                    .font(TowerDesign.Font.rowTitle.weight(.medium))
                    .foregroundStyle(.primary)
                    .lineLimit(1)
                    .contentTransition(.opacity)
                if !compact {
                    Text(model.keepAwakeLine)
                        .font(TowerDesign.Font.activity).foregroundStyle(.secondary)
                        .lineLimit(1)
                        .contentTransition(.opacity)
                }
            }
            Spacer(minLength: 8)
            AwakeModeSwitch(model: model)
        }
        .padding(.horizontal, TowerDesign.Size.padH)
        .padding(.vertical, compact ? 5 : 8)
    }
}

/// Off · lid open · lid closed, as one quiet capsule. The selected thumb slides
/// (settle spring; a fade under Reduce Motion) and moves only once the daemon
/// has actually taken the mode — the control shows truth, not intent.
struct AwakeModeSwitch: View {
    @ObservedObject var model: TowerModel
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Namespace private var thumb
    @State private var hovered: String?

    private static let modes: [(mode: String, symbol: String, help: String)] = [
        ("off", "moon.zzz", "Sleep allowed"),
        ("idle", "laptopcomputer", "Stay awake while agents work — lid open"),
        ("clamshell", "laptopcomputer.and.arrow.down",
         "Stay awake while agents work — even with the lid closed"),
    ]

    var body: some View {
        let current = model.keepAwakeMode
        HStack(spacing: 2) {
            ForEach(Self.modes, id: \.mode) { m in
                let on = m.mode == current
                Button {
                    guard !on else { return }
                    model.send(["cmd": "keepawake", "on": m.mode != "off", "mode": m.mode])
                } label: {
                    Image(systemName: m.symbol)
                        .font(.system(size: 11, weight: on ? .semibold : .regular))
                        .foregroundStyle(on ? AnyShapeStyle(.primary)
                                         : hovered == m.mode ? AnyShapeStyle(.secondary)
                                         : AnyShapeStyle(.tertiary))
                        .frame(width: 28, height: 20)
                        .background {
                            if on {
                                Capsule(style: .continuous)
                                    .fill(Color.primary.opacity(0.13))
                                    .overlay(Capsule(style: .continuous)
                                        .strokeBorder(Color.primary.opacity(0.10), lineWidth: 0.5))
                                    .shadow(color: .black.opacity(0.18), radius: 1.5, y: 0.5)
                                    .matchedGeometryEffect(id: "thumb", in: thumb)
                            }
                        }
                        .contentShape(Capsule())
                }
                .buttonStyle(.plain)
                .onHover { hovered = $0 ? m.mode : (hovered == m.mode ? nil : hovered) }
                .help(m.help)
                .accessibilityLabel(m.help)
                .accessibilityAddTraits(on ? .isSelected : [])
            }
        }
        .padding(2)
        .background(Capsule(style: .continuous).fill(Color.primary.opacity(0.05)))
        .animation(.tower(TowerDesign.Motion.settle, reduced: reduceMotion), value: current)
    }
}

// --------------------------------------------------------------------------- //
// Plan usage — the feed bill. The limits you track, as rings (Activity-style)
// or as slim bars (Settings → Popover → Plan usage style). White until your
// warn line, then yellow, then red — color only when it means something.
// --------------------------------------------------------------------------- //
struct PlanSection: View {
    @ObservedObject var model: TowerModel
    @AppStorage(PopPref.planStyle) private var style = "rings"
    // Read so a switch in Settings re-renders at once.
    @AppStorage(PopPref.limitSession) private var trackSession = true
    @AppStorage(PopPref.limitWeek) private var trackWeek = true
    @AppStorage(PopPref.limitFable) private var trackFable = true
    @AppStorage("warnAt") private var warn = 60
    @AppStorage("dangerAt") private var danger = 85
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        let plan = model.state?.plan
        let fetching = plan?.refreshing == true
        VStack(alignment: .leading, spacing: 9) {
            HStack {
                Text("PLAN USAGE").font(TowerDesign.Font.caption.weight(.heavy))
                    .tracking(0.7).foregroundStyle(.secondary)
                Spacer()
                if let p = plan, p.ok == true, model.usageGate == nil { Text(headerLine(p, fetching: fetching))
                    .font(TowerDesign.Font.caption).monospacedDigit().foregroundStyle(.tertiary) }
            }
            if model.usageGate != nil {
                // Guard isn't passing Claude → /usage can't be read. One calm
                // row that says why (connection vs location/VPN).
                UsagePaused(model: model)
            } else if let p = plan, p.disabled == true {
                Text("Live limits are off — no Claude runs, no permission prompts.")
                    .font(TowerDesign.Font.caption).foregroundStyle(.secondary)
            } else if let p = plan, p.ok == true {
                let limits = PopPref.trackedLimits(p)
                Group {
                    if style == "bars" {
                        VStack(spacing: 9) {
                            ForEach(limits, id: \.label) { l in bar(l.label, l.bucket) }
                        }
                    } else {
                        HStack(spacing: 0) {
                            ForEach(limits, id: \.label) { l in ring(l.label, l.bucket) }
                        }
                    }
                }
                .transition(.opacity)
                .shimmer(fetching)
            } else if let e = plan?.error {
                Text("unavailable — \(e)").font(TowerDesign.Font.caption)
                    .foregroundStyle(.orange)
            } else {
                HStack(spacing: 6) {
                    ProgressView().controlSize(.small)
                    Text("reading /usage…").font(TowerDesign.Font.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .padding(.horizontal, TowerDesign.Size.padH)
        .padding(.vertical, 8)
        .animation(.tower(TowerDesign.Motion.settle, reduced: reduceMotion), value: style)
    }

    /// "$165 today · 5s ago" — the day's estimated cost rides the header, so
    /// the section stays two rows of signal.
    private func headerLine(_ p: GPlan, fetching: Bool) -> String {
        let cost = (model.state?.usage?.today?.cost ?? 0) > 0
            ? "\(fmtCost(model.state?.usage?.today?.cost ?? 0)) today · " : ""
        if fetching { return cost + "updating…" }
        return cost + (p.updated.map { "\(agoString(sinceEpoch: $0)) ago" } ?? "")
    }

    @ViewBuilder func ring(_ label: String, _ b: GPlanBucket?) -> some View {
        if let b, let pct = b.pct {
            HStack(spacing: 8) {
                ZStack {
                    RingGauge(fraction: Double(pct) / 100, tint: tint(pct), lineWidth: 4.5)
                    Text("\(pct)")
                        .font(.system(size: 11, weight: .semibold, design: .rounded))
                        .monospacedDigit()
                        .contentTransition(.numericText())
                }
                .frame(width: 34, height: 34)
                VStack(alignment: .leading, spacing: 1) {
                    Text(label).font(.system(size: 12, weight: .medium)).lineLimit(1)
                    resetLabel(b)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .help(tooltip(label, pct, b))
            .animation(TowerDesign.Motion.settle, value: pct)
        }
    }

    @ViewBuilder func bar(_ label: String, _ b: GPlanBucket?) -> some View {
        if let b, let pct = b.pct {
            VStack(spacing: 5) {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text(label).font(.system(size: 12, weight: .medium))
                    Spacer(minLength: 6)
                    resetLabel(b)
                    Text("\(pct)%")
                        .font(.system(size: 12, weight: .semibold, design: .rounded))
                        .monospacedDigit()
                        .foregroundStyle(pct >= warnAt() ? AnyShapeStyle(tint(pct)) : AnyShapeStyle(.primary))
                        .contentTransition(.numericText())
                        .frame(minWidth: 34, alignment: .trailing)
                }
                ShareBar(fraction: Double(pct) / 100, tint: tint(pct))
                    .frame(height: 4)
            }
            .help(tooltip(label, pct, b))
            .animation(TowerDesign.Motion.settle, value: pct)
        }
    }

    /// "↻ 6d 14h" — one line, never wraps; hover for the reset's clock time.
    private func resetLabel(_ b: GPlanBucket) -> some View {
        HStack(spacing: 3) {
            Image(systemName: "arrow.clockwise").font(.system(size: 7.5, weight: .semibold))
            Text(b.resetShort ?? "—").monospacedDigit()
        }
        .font(TowerDesign.Font.caption.weight(.medium))
        .foregroundStyle(.tertiary)
        .lineLimit(1)
        .fixedSize()
    }

    private func tooltip(_ label: String, _ pct: Int, _ b: GPlanBucket) -> String {
        b.resets_at.map { "\(label): \(pct)% used · resets \(resetClock($0)) (\(b.resetDisplay ?? ""))" }
            ?? "\(label): \(pct)% used"
    }

    /// White below the warn line, then yellow, then red — the user's thresholds.
    func tint(_ pct: Int) -> Color {
        pct >= danger ? Color(nsColor: .systemRed)
            : pct >= warn ? Color(nsColor: .systemYellow) : Color.primary
    }
}

// --------------------------------------------------------------------------- //
// Footer — one slim bar: the dashboard as the primary pill (it's where every
// deeper control lives, Settings included), then the terminal and quit as
// quiet round icons. Quit sits apart and still asks twice.
// --------------------------------------------------------------------------- //
struct PopFooter: View {
    @ObservedObject var model: TowerModel
    var body: some View {
        HStack(spacing: 6) {
            FooterPill(symbol: "macwindow", title: "Open Dashboard", key: "d") {
                (NSApp.delegate as? AppDelegate)?.openDashboard(tab: .overview)
            }
            FooterIcon(symbol: "gearshape", help: "Settings — customize this popover", key: ",") {
                (NSApp.delegate as? AppDelegate)?.openDashboard(tab: .settings)
            }
            FooterIcon(symbol: "terminal", help: "Open the terminal dashboard", key: "t") {
                (NSApp.delegate as? AppDelegate)?.openTerminalDashboard()
            }
            FooterIcon(symbol: "power", help: "Quit Tower and stop the guard — asks twice",
                       key: "q", danger: true) {
                (NSApp.delegate as? AppDelegate)?.confirmQuit()
            }
        }
        .padding(.horizontal, 8).padding(.vertical, 7)
    }
}

struct FooterPill: View {
    let symbol: String
    let title: String
    let key: KeyEquivalent
    let action: () -> Void
    @State private var hovering = false
    @State private var pressed = false
    var body: some View {
        Button(action: action) {
            HStack(spacing: 7) {
                Image(systemName: symbol).font(.system(size: 12, weight: .medium))
                Text(title).font(.system(size: 12, weight: .medium))
                Spacer(minLength: 4)
                Text("⌘\(String(key.character).uppercased())")
                    .font(.system(size: 10, weight: .medium)).foregroundStyle(.tertiary)
            }
            .foregroundStyle(hovering ? .primary : .secondary)
            .padding(.horizontal, 11).frame(height: 30)
            .background(Capsule(style: .continuous)
                .fill(Color.primary.opacity(hovering ? 0.10 : 0.055)))
            .scaleEffect(pressed ? 0.97 : 1)
            .contentShape(Capsule(style: .continuous))
        }
        .buttonStyle(PressReporting(pressed: $pressed))
        .keyboardShortcut(key, modifiers: .command)
        .onHover { h in withAnimation(.easeOut(duration: 0.12)) { hovering = h } }
        .animation(.spring(response: 0.25, dampingFraction: 0.7), value: pressed)
    }
}

struct FooterIcon: View {
    let symbol: String
    let help: String
    let key: KeyEquivalent
    var danger = false
    let action: () -> Void
    @State private var hovering = false
    @State private var pressed = false
    var body: some View {
        Button(action: action) {
            Image(systemName: symbol)
                .font(.system(size: 12, weight: .medium))
                .foregroundStyle(danger && hovering ? AnyShapeStyle(Color(nsColor: .systemRed))
                                 : hovering ? AnyShapeStyle(.primary) : AnyShapeStyle(.secondary))
                .frame(width: 30, height: 30)
                .background(Circle().fill(danger && hovering ? Color.red.opacity(0.14)
                                          : Color.primary.opacity(hovering ? 0.10 : 0.055)))
                .scaleEffect(pressed ? 0.92 : 1)
                .contentShape(Circle())
        }
        .buttonStyle(PressReporting(pressed: $pressed))
        .keyboardShortcut(key, modifiers: .command)
        .help(help)
        .onHover { h in withAnimation(.easeOut(duration: 0.12)) { hovering = h } }
        .animation(.spring(response: 0.25, dampingFraction: 0.7), value: pressed)
    }
}

/// A plain button style that reports its pressed state, so a tile can give
/// the tactile little press every native control has.
struct PressReporting: ButtonStyle {
    @Binding var pressed: Bool
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .onChange(of: configuration.isPressed) { _, p in pressed = p }
    }
}

/// Counts as SF Symbols with their numbers — "〰 1   ✓ 2" — the words live in
/// the tooltip. Zero counts drop out; nothing at all reads "quiet".
struct SummaryCounts: View {
    let items: [(Int, String, String, Color)]
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    var body: some View {
        let shown = items.filter { $0.0 > 0 }
        HStack(spacing: 10) {
            if shown.isEmpty {
                Text("quiet").font(TowerDesign.Font.counter).foregroundStyle(.tertiary)
            }
            ForEach(shown, id: \.1) { n, symbol, word, tint in
                HStack(spacing: 3) {
                    Image(systemName: symbol)
                        .font(.system(size: 9.5, weight: .semibold))
                        .foregroundStyle(tint == .primary ? AnyShapeStyle(.secondary) : AnyShapeStyle(tint))
                        .symbolEffect(.variableColor.iterative, isActive: symbol == "waveform" && !reduceMotion)
                    Text("\(n)")
                        .font(.system(size: 11, weight: .semibold)).monospacedDigit()
                        .foregroundStyle(tint == .secondary ? AnyShapeStyle(.secondary) : AnyShapeStyle(.primary))
                        .contentTransition(.numericText())
                }
                .help("\(n) \(word)")
                .accessibilityElement(children: .ignore)
                .accessibilityLabel("\(n) \(word)")
                .transition(.opacity.combined(with: .scale(scale: 0.8)))
            }
        }
        .animation(.tower(TowerDesign.Motion.settle, reduced: reduceMotion), value: shown.map(\.0))
    }
}

/// /usage is paused because the guard isn't passing Claude. One calm row in
/// the same shape as every other: a tinted mark tile, what's paused, and the
/// honest why — the connection or the location — and that it comes back alone.
struct UsagePaused: View {
    @ObservedObject var model: TowerModel
    var body: some View {
        let net = model.state?.plan?.gate_reason == "net" || model.state?.guardInfo?.net_ok == false
        let amber = Color(nsColor: .systemOrange)
        HStack(spacing: 11) {
            RoundedRectangle(cornerRadius: 7, style: .continuous)
                .fill(amber.opacity(0.14))
                .overlay(Image(systemName: net ? "wifi.slash" : "location.slash.fill")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(amber))
                .frame(width: 28, height: 28)
            VStack(alignment: .leading, spacing: 2) {
                Text("Usage paused").font(.system(size: 13, weight: .semibold))
                Text(net ? "Waiting for a stable connection to Anthropic"
                         : "Waiting to confirm you’re in \(flag(model.targetCC)) \(model.targetName)")
                    .font(TowerDesign.Font.activity).foregroundStyle(.secondary)
                    .lineLimit(1).truncationMode(.tail)
            }
            Spacer(minLength: 0)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .help(model.usageGate?.detail ?? "")
        .transition(.opacity)
    }
}
