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
    @Namespace private var agentSpace

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
                // cosmetic: the middle reorders under an animation
                // (matchedGeometry + the reorder spring) whenever an agent moves
                // section (working → done → resting). Mid-animation the column's
                // height briefly overshoots the 460 cap, which hands the
                // ScrollView a transient scroll range; without a pinned anchor it
                // lands at a NON-zero content offset and STICKS there after the
                // content settles back under the cap — with no scrollable range
                // left to correct it. That is the recurring "UI shifted out of
                // view" bug: horizontally it centered an over-wide frame (fixed
                // by the leading pin below), vertically it stranded the top rows
                // (NetRow + the AGENTS header) above the fold. Anchoring
                // top-leading forces the resting position back to the origin on
                // every content-size change, on both axes, so no reflow can leave
                // a stuck offset.
                ScrollView {
                    VStack(spacing: 0) {
                        NetRow(model: model)
                        Divider().padding(.horizontal, TowerDesign.Size.padH)
                        AgentsSection(model: model, space: agentSpace)
                        Divider().padding(.horizontal, TowerDesign.Size.padH)
                        LocationRow(model: model)
                        Divider().padding(.horizontal, TowerDesign.Size.padH)
                        PlanSection(model: model)
                    }
                    // WHY the popover used to lurch left after a status/agent
                    // update (the recurring clipped-label bug): a vertical
                    // ScrollView *horizontally centers* any content wider than
                    // its content viewport, and that offset STICKS until reopen.
                    // Header/footer live outside the ScrollView, so only the
                    // middle column drifts.
                    //
                    // The subtlety that kept this "fixed but not fixed": pinning
                    // the content to the *constant* popoverWidth does NOT match
                    // it to the viewport. The ScrollView's real content width
                    // can differ from popoverWidth by a hair (safe-area / inset
                    // / a reflow frame), and the instant the fixed-360 column is
                    // even 1pt wider than the viewport it sits in, it gets
                    // centered → leading edge goes negative → "AGENTS"→"GENTS"
                    // and the radar marks clip off the left edge.
                    //
                    // The real cure is to let the column *track the viewport*
                    // (maxWidth: .infinity) rather than assert a constant width:
                    // content then equals the viewport by construction, so there
                    // is never any overflow for the ScrollView to center. Leading
                    // alignment keeps the origin fixed, and .clipped() trims any
                    // transient per-row overflow (a numericText digit tick, a
                    // matchedGeometry reorder frame) inside the column instead of
                    // letting it disturb the origin or escape the popover.
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .clipped()
                }
                .frame(width: TowerDesign.Size.popoverWidth)
                .frame(maxHeight: 460)
                .clipped()
                .defaultScrollAnchor(.topLeading)
                .scrollBounceBehavior(.basedOnSize)
            }
            Divider()
            PopFooter(model: model)
        }
        .frame(width: TowerDesign.Size.popoverWidth)
        .animation(.tower(TowerDesign.Motion.settle, reduced: reduceMotion), value: model.alive)
        .dangerAlerts(model)
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
        HStack(spacing: 10) {
            TowerRadar(state: model.radarState, size: 30, color: .primary)
                .frame(width: 30, height: 30)
            VStack(alignment: .leading, spacing: 1) {
                Text("Tower").font(TowerDesign.Font.header)
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
                    Text(st.title)
                        .font(TowerDesign.Font.activity)
                        .foregroundStyle(st.swiftUIColor)
                        .contentTransition(.opacity)
                }
            }
            Spacer()
            Toggle("", isOn: Binding(get: { routed }, set: { on in
                if on { model.send(["cmd": "route", "on": true]) }
                else { model.requestDanger(
                    "Turn off the guard?",
                    "This removes routing from settings.json and Claude Code "
                    + "connects DIRECTLY to the API — with no country guard at "
                    + "all.",
                    confirm: "Turn off guard") {
                    model.send(["cmd": "route", "on": false]) } }
            }))
                .labelsHidden().toggleStyle(.switch).controlSize(.small)
                .help("Route Claude through the guard")
        }
        .padding(.horizontal, TowerDesign.Size.padH)
        .padding(.vertical, 10)
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
            HStack(spacing: 6) {
                Circle().fill(Color(nsColor: .systemGreen)).frame(width: 6, height: 6)
                Text("Internet · API").font(.system(size: 12))
                Spacer()
                Text("\(fmtMs(net?.internet_ms)) · \(fmtMs(net?.api_ms))")
                    .font(TowerDesign.Font.counter).foregroundStyle(.secondary)
            }
            .padding(.horizontal, TowerDesign.Size.padH)
            .padding(.vertical, 6)
        case .degraded:
            banner(icon: "wifi.exclamationmark", color: .orange,
                   title: net?.reason == "dns" ? "DNS problem" : "Internet is slow",
                   sub: "ping \(fmtMs(net?.internet_ms)) — expect Claude timeouts")
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
                    Text(summary(summaryInfo, needs: needs.count))
                        .font(TowerDesign.Font.counter)
                        .foregroundStyle(.secondary)
                        .contentTransition(.numericText())
                }
                .padding(.horizontal, TowerDesign.Size.padH)
                .padding(.top, 8).padding(.bottom, 4)

                ForEach(needs) { s in
                    NeedsYouRow(model: model, session: s)
                        .matchedGeometryEffect(id: s.id, in: space)
                }

                ForEach(model.collisions) { c in
                    CollisionBanner(collision: c)
                }

                ForEach(working) { s in
                    AgentRow(model: model, session: s)
                        .matchedGeometryEffect(id: s.id, in: space)
                }

                if needs.isEmpty && working.isEmpty {
                    EmptyState(anyResting: !resting.isEmpty)
                }

                if !resting.isEmpty {
                    DisclosureGroup(isExpanded: $showResting) {
                        ForEach(resting) { s in RestingRow(session: s) }
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
                   value: model.agentSessions.map(\.id) + needs.map { $0.status ?? "" })
    }

    func summary(_ h: GAgentSummary?, needs: Int) -> String {
        var parts: [String] = []
        if let w = h?.working, w > 0 { parts.append("\(w) at work") }
        if let d = h?.done_today, d > 0 { parts.append("\(d) jobs done today") }
        if needs > 0 { parts.append("\(needs) need\(needs == 1 ? "s" : "") you") }
        return parts.isEmpty ? "quiet" : parts.joined(separator: " · ")
    }
}

// A needs-you row: distinct symbol shape + color + position per state.
// Done pops and glows once; failure arrives sober. Click = focus.
struct NeedsYouRow: View {
    @ObservedObject var model: TowerModel
    let session: GAgentSession
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var glow = false
    @State private var copied = false
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
                    ModelBadge(session: session)
                }
                Text(copied ? "resume command copied — paste in any terminal"
                            : rowSubtitle(session, st))
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
        var out = st.phrase
        if let t = s.title ?? s.last_prompt, !t.isEmpty {
            out += " · \(t)"
        }
        return out
    }

    func focus() {
        if session.focusable == true {
            model.send(["cmd": "focus", "session_id": session.id])
        } else {
            // Background job — no terminal to raise. First-class fallback:
            // put the resume command on the clipboard.
            let pb = NSPasteboard.general
            pb.clearContents()
            pb.setString("claude --resume \(session.id)", forType: .string)
            copied = true
            DispatchQueue.main.asyncAfter(deadline: .now() + 2.5) { copied = false }
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

// A working row: the model's mark is alive; the activity line shimmers only
// while a tool call is actually in flight. Momentum counter ticks up.
struct AgentRow: View {
    @ObservedObject var model: TowerModel
    let session: GAgentSession
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var hovering = false

    var body: some View {
        let tier = ModelTier(family: session.model_family)
        let tooling = session.pending_tool != nil
        HStack(spacing: 9) {
            ModelGlyphView(tier: tier, working: true)
            VStack(alignment: .leading, spacing: 1) {
                HStack(spacing: 6) {
                    Text(session.project_name ?? "agent")
                        .font(TowerDesign.Font.rowTitle.weight(.medium))
                        .foregroundStyle(.primary)      // the name: one color
                        .lineLimit(1)
                    ModelBadge(session: session)
                    if session.health?.level == "warn" {
                        Image(systemName: "exclamationmark.triangle.fill")
                            .font(.system(size: 9))
                            .foregroundStyle(Color(nsColor: .systemYellow))
                            .help((session.health?.reasons ?? []).joined(separator: "\n"))
                    }
                }
                HStack(spacing: 4) {
                    if tooling {
                        ProgressView().controlSize(.mini)
                    }
                    Text(session.activity ?? "thinking…")
                        .font(TowerDesign.Font.activity)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                        .shimmer(tooling && !reduceMotion)
                }
            }
            Spacer()
            if let done = session.ticks?.tools_done, done > 0 {
                Text("\(done) ✓")
                    .font(TowerDesign.Font.counter)
                    .foregroundStyle(.tertiary)
                    .contentTransition(.numericText())
            }
            Text(agoString(sinceEpoch: session.last_activity ?? Date().timeIntervalSince1970))
                .font(TowerDesign.Font.counter).foregroundStyle(.tertiary)
        }
        .padding(.horizontal, TowerDesign.Size.padH)
        .padding(.vertical, TowerDesign.Size.rowVPad)
        .background(
            RoundedRectangle(cornerRadius: 8, style: .continuous)
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
// Location — where the fence thinks you are. Keep-awake shows as a glyph only
// (the control moved to the dashboard).
// --------------------------------------------------------------------------- //
struct LocationRow: View {
    @ObservedObject var model: TowerModel
    var body: some View {
        let loc = model.state?.location
        let target = model.state?.guardInfo?.target_cc ?? "—"
        let ok = loc?.status == "OK"
        let inTarget = loc?.in_target ?? false
        HStack(spacing: 7) {
            Text(flag(ok ? loc?.country_cc : target)).font(.system(size: 13))
            if model.netStatus == .offline {
                Text("internet down — location unknown, not blocking")
                    .font(.system(size: 12)).foregroundStyle(Color(nsColor: .systemRed))
            } else if ok {
                Text("\(loc?.city ?? "?"), \(loc?.country_cc ?? "?")")
                    .font(.system(size: 12))
                Text(inTarget ? "— inside \(flag(target)) \(target)"
                              : "— outside \(flag(target)) \(target)")
                    .font(.system(size: 12))
                    .foregroundStyle(inTarget ? Color.secondary : Color.orange)
            } else {
                Text("Locating… (allowing)").font(.system(size: 12))
                    .foregroundStyle(.secondary)
            }
            Spacer()
            if model.state?.keepawake?.on == true {
                Image(systemName: "moon.zzz.fill")
                    .font(.system(size: 10)).foregroundStyle(.secondary)
                    .help("Keep-awake is on (control in the dashboard)")
            }
            Button {
                model.send(["cmd": "recheck"])
            } label: {
                Image(systemName: "arrow.clockwise").font(.system(size: 10, weight: .medium))
            }
            .buttonStyle(.borderless)
            .help("Re-check location now")
        }
        .padding(.horizontal, TowerDesign.Size.padH)
        .padding(.vertical, 6)
    }
}

// --------------------------------------------------------------------------- //
// Plan usage — the feed bill. Three compact meters.
// --------------------------------------------------------------------------- //
struct PlanSection: View {
    @ObservedObject var model: TowerModel
    var body: some View {
        let plan = model.state?.plan
        let fetching = plan?.refreshing == true
        VStack(alignment: .leading, spacing: 7) {
            HStack {
                Text("PLAN USAGE").font(TowerDesign.Font.caption.weight(.heavy))
                    .tracking(0.7).foregroundStyle(.secondary)
                Spacer()
                if let p = plan, p.ok == true {
                    Text(fetching ? "updating…"
                         : (p.updated.map { "updated \(agoString(sinceEpoch: $0)) ago" } ?? ""))
                        .font(TowerDesign.Font.caption).foregroundStyle(.tertiary)
                }
            }
            if let gate = model.usageGate {
                // Guard isn't passing Claude → /usage can't be read. Say why
                // (connection vs location/VPN), with room to breathe.
                VStack(spacing: 7) {
                    Image(systemName: model.state?.guardInfo?.net_ok == false
                          ? "wifi.exclamationmark" : "location.slash")
                        .font(.system(size: 20, weight: .regular))
                        .foregroundStyle(.orange)
                    Text(gate.headline)
                        .font(.system(size: 12, weight: .semibold))
                    Text(gate.detail)
                        .font(TowerDesign.Font.caption).foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 16)
            } else if let p = plan, p.disabled == true {
                Text("Live limits are off — no Claude runs, no permission prompts.")
                    .font(TowerDesign.Font.caption).foregroundStyle(.secondary)
            } else if let p = plan, p.ok == true {
                VStack(alignment: .leading, spacing: 7) {
                    meter("Session", p.session)
                    meter("Weekly", p.week)
                    meter("Fable", p.fable)
                }
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
    }

    @ViewBuilder func meter(_ label: String, _ b: GPlanBucket?) -> some View {
        if let b = b, let pct = b.pct {
            VStack(alignment: .leading, spacing: 3) {
                HStack(alignment: .firstTextBaseline) {
                    Text(label).font(.system(size: 12, weight: .medium))
                    Spacer()
                    Text("\(pct)%")
                        .font(.system(size: 13, weight: .bold))
                        .monospacedDigit().foregroundStyle(levelColor(pct))
                        .contentTransition(.numericText())
                    if let r = b.resetDisplay {
                        Text("resets \(r)").font(TowerDesign.Font.caption)
                            .foregroundStyle(.tertiary)
                    }
                }
                Meter(fraction: min(max(Double(pct) / 100.0, 0), 1), color: levelColor(pct))
                    .frame(height: 4)
            }
            .animation(TowerDesign.Motion.settle, value: pct)
        }
    }
}

// --------------------------------------------------------------------------- //
// Footer — menu-item style rows.
// --------------------------------------------------------------------------- //
struct PopFooter: View {
    @ObservedObject var model: TowerModel
    var body: some View {
        VStack(spacing: 0) {
            footerButton("gauge.with.dots.needle.67percent", "Open Dashboard…") {
                (NSApp.delegate as? AppDelegate)?.openDashboard(tab: .overview)
            }
            footerButton("gearshape", "Settings…") {
                (NSApp.delegate as? AppDelegate)?.openDashboard(tab: .settings)
            }
            footerButton("power", "Quit & Stop Guard…") {
                (NSApp.delegate as? AppDelegate)?.confirmQuit()
            }
        }
        .padding(.vertical, 4)
    }

    func footerButton(_ icon: String, _ title: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 8) {
                Image(systemName: icon).font(.system(size: 11)).frame(width: 16)
                Text(title).font(.system(size: 13))
                Spacer()
            }
            .contentShape(Rectangle())
            .padding(.horizontal, TowerDesign.Size.padH)
            .padding(.vertical, 5)
        }
        .buttonStyle(.borderless)
    }
}
