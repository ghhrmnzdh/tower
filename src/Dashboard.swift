// Tower — the dashboard window: everything that doesn't belong in a glance.
// Five tabs: Overview (guard + controls), Network (weather), Usage (feed
// bill), Agents (every session, full detail), Settings.

import AppKit
import SwiftUI
import Charts

enum DashboardTab: String, CaseIterable, Identifiable {
    case overview, network, usage, agents, settings
    var id: String { rawValue }
    var title: String {
        switch self {
        case .overview: return "Overview"; case .network: return "Network"
        case .usage: return "Usage"; case .agents: return "Agents"
        case .settings: return "Settings"
        }
    }
    var symbol: String {
        switch self {
        case .overview: return "shield.lefthalf.filled"
        case .network:  return "wifi"
        case .usage:    return "chart.bar.xaxis"
        case .agents:   return "dot.radiowaves.left.and.right"
        case .settings: return "gearshape"
        }
    }
}

final class DashboardWindowController {
    private var window: NSWindow?
    private let model: TowerModel
    private let selected = SelectedTab()

    init(model: TowerModel) { self.model = model }

    func open(tab: DashboardTab) {
        selected.tab = tab
        if window == nil {
            let w = NSWindow(
                contentRect: NSRect(x: 0, y: 0, width: 700, height: 470),
                styleMask: [.titled, .closable, .miniaturizable, .resizable],
                backing: .buffered, defer: false)
            w.title = "Tower"
            w.isReleasedWhenClosed = false
            w.minSize = NSSize(width: 640, height: 420)
            w.center()
            w.contentViewController = NSHostingController(
                rootView: DashboardView(model: model, selected: selected))
            window = w
        }
        NSApp.activate(ignoringOtherApps: true)
        window?.makeKeyAndOrderFront(nil)
    }
}

final class SelectedTab: ObservableObject {
    @Published var tab: DashboardTab = .overview
}

struct DashboardView: View {
    @ObservedObject var model: TowerModel
    @ObservedObject var selected: SelectedTab

    var body: some View {
        NavigationSplitView {
            List(DashboardTab.allCases, selection: Binding(
                get: { Optional(selected.tab) },
                set: { selected.tab = $0 ?? .overview })) { tab in
                Label(tab.title, systemImage: tab.symbol).tag(tab)
            }
            .navigationSplitViewColumnWidth(min: 150, ideal: 160, max: 200)
        } detail: {
            ScrollView {
                Group {
                    switch selected.tab {
                    case .overview: OverviewTab(model: model)
                    case .network:  NetworkTab(model: model)
                    case .usage:    UsageTab(model: model)
                    case .agents:   AgentsTab(model: model)
                    case .settings: SettingsTab(model: model)
                    }
                }
                .padding(16)
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .transition(.opacity)
            .animation(.easeInOut(duration: 0.15), value: selected.tab)
        }
        .dangerAlerts(model)
    }
}

// --------------------------------------------------------------------------- //
// Overview
// --------------------------------------------------------------------------- //
struct OverviewTab: View {
    @ObservedObject var model: TowerModel
    var body: some View {
        let st = model.status
        let loc = model.state?.location
        let g = model.state?.guardInfo
        VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 14) {
                ZStack {
                    Circle().fill(st.swiftUIColor.opacity(0.15)).frame(width: 56, height: 56)
                    Image(systemName: st.symbol)
                        .font(.system(size: 26, weight: .semibold))
                        .foregroundStyle(st.swiftUIColor)
                }
                VStack(alignment: .leading, spacing: 2) {
                    Text(st.title).font(.system(size: 18, weight: .bold))
                    if let loc = loc, loc.status == "OK" {
                        Text("\(loc.city ?? "?"), \(loc.region ?? "?") · \(loc.isp ?? "?") · \(loc.ip ?? "?")")
                            .font(.system(size: 11)).foregroundStyle(.secondary)
                    } else {
                        Text(loc?.error ?? "locating…")
                            .font(.system(size: 11)).foregroundStyle(.secondary)
                    }
                }
                Spacer()
            }

            GroupBox("Controls") {
                ControlsPane(model: model).padding(6)
            }

            GroupBox("Counters") {
                HStack(spacing: 18) {
                    counter("Allowed", g?.allowed)
                    counter("Blocked", g?.blocked)
                    counter("Proxy port", g?.proxy_port)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Guard PID").font(.system(size: 10)).foregroundStyle(.secondary)
                        Text(model.state?.procs?.daemon_pid.map(String.init) ?? "—")
                            .font(.system(size: 14, weight: .semibold)).monospacedDigit()
                    }
                    Spacer()
                }
                .padding(6)
            }
        }
    }
    func counter(_ label: String, _ v: Int?) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label).font(.system(size: 10)).foregroundStyle(.secondary)
            Text(v.map(String.init) ?? "—")
                .font(.system(size: 14, weight: .semibold)).monospacedDigit()
                .contentTransition(.numericText())
        }
    }
}

// Full controls — everything that left the popover lives here.
struct ControlsPane: View {
    @ObservedObject var model: TowerModel
    var body: some View {
        let g = model.state?.guardInfo
        let routed = model.state?.routing?.installed ?? false
        VStack(spacing: 8) {
            Toggle(isOn: Binding(get: { routed }, set: { on in
                if on { model.send(["cmd": "route", "on": true]) }
                else { model.requestDanger(
                    "Turn off the guard?",
                    "This removes routing from settings.json and Claude Code "
                    + "connects DIRECTLY to the API — with no country guard at "
                    + "all.",
                    confirm: "Turn off guard") {
                    model.send(["cmd": "route", "on": false]) } }
            })) {
                Label("Route Claude through guard", systemImage: "arrow.triangle.branch")
            }.toggleStyle(.switch)
            Divider()
            row("Enforce (block outside)") {
                Toggle("", isOn: Binding(get: { g?.enforce ?? true }, set: { on in
                    if on { model.send(["cmd": "enforce", "on": true]) }
                    else { model.requestDanger(
                        "Stop enforcing the guard?",
                        "Claude will still route through the guard, but requests "
                        + "are NO LONGER blocked when you're outside "
                        + "\(g?.target_cc ?? "your country").",
                        confirm: "Stop enforcing") {
                        model.send(["cmd": "enforce", "on": false]) } }
                }))
                    .labelsHidden().toggleStyle(.switch).controlSize(.small)
            }
            row("Scope") {
                Menu(g?.block_all == true ? "All traffic" : "Claude only") {
                    Button("Claude only") { model.send(["cmd": "scope", "block_all": false]) }
                    Button("All traffic") { model.send(["cmd": "scope", "block_all": true]) }
                }.fixedSize()
            }
            row("Country") {
                Menu {
                    ForEach(COUNTRIES, id: \.cc) { c in
                        Button("\(flag(c.cc)) \(c.name)") {
                            model.send(["cmd": "country", "cc": c.cc])
                        }
                    }
                } label: { Text("\(flag(g?.target_cc)) \(g?.target_cc ?? "US")") }
                    .fixedSize()
            }
            row("Keep awake") { KeepAwakeMenu(model: model) }
        }
    }
    @ViewBuilder func row<T: View>(_ t: String, @ViewBuilder _ trailing: () -> T) -> some View {
        HStack {
            Text(t).font(.system(size: 12)).foregroundStyle(.secondary)
            Spacer()
            trailing()
        }
    }
}

// --------------------------------------------------------------------------- //
// Network — the weather station.
// --------------------------------------------------------------------------- //
struct NetworkTab: View {
    @ObservedObject var model: TowerModel
    var body: some View {
        let net = model.state?.net
        VStack(alignment: .leading, spacing: 14) {
            NetRow(model: model)   // same verdict component, wider canvas

            GroupBox("Latency — last \(max((net?.history?.count ?? 0) / 6, 1)) min") {
                if let hist = net?.history, hist.count > 1 {
                    Chart {
                        ForEach(Array(hist.enumerated()), id: \.offset) { _, s in
                            if let t = s.t, let v = s.internet_ms {
                                LineMark(x: .value("t", Date(timeIntervalSince1970: t)),
                                         y: .value("ms", v),
                                         series: .value("kind", "Internet"))
                                    .foregroundStyle(by: .value("kind", "Internet"))
                            }
                            if let t = s.t, let v = s.api_ms {
                                LineMark(x: .value("t", Date(timeIntervalSince1970: t)),
                                         y: .value("ms", v),
                                         series: .value("kind", "Anthropic API"))
                                    .foregroundStyle(by: .value("kind", "Anthropic API"))
                            }
                        }
                    }
                    .chartYAxisLabel("ms")
                    .frame(height: 160)
                    .padding(6)
                } else {
                    Text("collecting samples…")
                        .font(.system(size: 11)).foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity, alignment: .center)
                        .padding(20)
                }
            }

            GroupBox("Speed test") {
                HStack(spacing: 12) {
                    let stst = net?.speedtest
                    Button("Run Speed Test") { model.send(["cmd": "speedtest"]) }
                        .disabled(stst?.running == true)
                    if stst?.running == true {
                        ProgressView(value: stst?.progress ?? 0)
                            .frame(width: 140)
                        Text("\(Int((stst?.progress ?? 0) * 100))%")
                            .font(.system(size: 11)).monospacedDigit()
                            .foregroundStyle(.secondary)
                    } else if let mbps = stst?.mbps_down {
                        Text(String(format: "↓ %.0f Mbps", mbps))
                            .font(.system(size: 14, weight: .semibold)).monospacedDigit()
                        if let at = stst?.at {
                            Text("as of \(agoString(sinceEpoch: at)) ago")
                                .font(.system(size: 11)).foregroundStyle(.secondary)
                        }
                    } else if let err = stst?.error {
                        Text(err).font(.system(size: 11)).foregroundStyle(.orange)
                    } else {
                        Text("never run").font(.system(size: 11)).foregroundStyle(.secondary)
                    }
                    Spacer()
                }
                .padding(6)
            }

            GroupBox("Live traffic") {
                let recent = Array((model.state?.recent ?? []).suffix(12).reversed())
                if recent.isEmpty {
                    Text("no traffic seen yet — route Claude through the guard first")
                        .font(.system(size: 11)).foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity, alignment: .center).padding(12)
                } else {
                    VStack(spacing: 3) {
                        ForEach(Array(recent.enumerated()), id: \.offset) { _, e in
                            HStack(spacing: 8) {
                                Text(e.t ?? "").font(.system(size: 10, design: .monospaced))
                                    .foregroundStyle(.secondary)
                                Text(e.host ?? "?").font(.system(size: 11)).lineLimit(1)
                                Spacer()
                                pill(e.kind == "claude" ? "claude" : "other",
                                     e.kind == "claude" ? .blue : .gray)
                                pill(e.action ?? "?",
                                     e.action == "blocked" ? .red : .green)
                            }
                        }
                    }
                    .padding(6)
                }
            }
        }
    }
    func pill(_ text: String, _ color: Color) -> some View {
        Text(text).font(.system(size: 9, weight: .semibold))
            .padding(.horizontal, 6).padding(.vertical, 1)
            .background(color.opacity(0.15), in: Capsule())
            .foregroundStyle(color)
    }
}

// --------------------------------------------------------------------------- //
// Usage — plan meters + local cost estimate.
// --------------------------------------------------------------------------- //
struct UsageTab: View {
    @ObservedObject var model: TowerModel
    var body: some View {
        let u = model.state?.usage
        let plan = model.state?.plan
        VStack(alignment: .leading, spacing: 14) {
            GroupBox {
                VStack(alignment: .leading, spacing: 10) {
                    HStack {
                        Text("Plan limits").font(.system(size: 12, weight: .semibold))
                        Spacer()
                        if let l24 = plan?.last24h {
                            Text("last 24h · \(l24.requests ?? 0) requests · \(l24.sessions ?? 0) sessions")
                                .font(.system(size: 10)).foregroundStyle(.secondary)
                        }
                        Button("Refresh") { model.send(["cmd": "refreshplan"]) }
                            .controlSize(.small)
                    }
                    if let gate = model.usageGate {
                        // Guard withholding /usage — explain, with breathing room.
                        VStack(spacing: 9) {
                            Image(systemName: model.state?.guardInfo?.net_ok == false
                                  ? "wifi.exclamationmark" : "location.slash")
                                .font(.system(size: 26, weight: .regular))
                                .foregroundStyle(.orange)
                            Text(gate.headline).font(.system(size: 13, weight: .semibold))
                            Text(gate.detail)
                                .font(.system(size: 11)).foregroundStyle(.secondary)
                                .multilineTextAlignment(.center)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 24)
                    } else if let p = plan, p.ok == true {
                        planMeter("Session", p.session)
                        planMeter("Weekly (all models)", p.week)
                        planMeter("Fable", p.fable)
                    } else {
                        Text(plan?.error ?? (plan?.disabled == true
                             ? "live limits are off (Settings)" : "reading /usage…"))
                            .font(.system(size: 11)).foregroundStyle(.secondary)
                    }
                }
                .padding(6)
            }

            GroupBox("Local estimate — list price, not your plan") {
                VStack(alignment: .leading, spacing: 10) {
                    HStack(spacing: 0) {
                        stat("Session", u?.session?.cost)
                        Divider().frame(height: 30)
                        stat("Today", u?.today?.cost)
                        Divider().frame(height: 30)
                        stat("Week", u?.week?.cost)
                    }
                    if let proj = u?.pace?.projected_week_cost, proj > 0 {
                        Text("on pace for ~\(fmtCost(proj)) this week")
                            .font(.system(size: 11)).foregroundStyle(.secondary)
                    }
                    if let bm = u?.byModel, !bm.isEmpty {
                        Divider()
                        ForEach(bm) { m in
                            HStack(spacing: 7) {
                                Circle().fill(ModelTier(modelID: m.model).accent)
                                    .frame(width: 6, height: 6)
                                Text(modelDisplay(m.model)).font(.system(size: 11, weight: .medium))
                                Meter(fraction: m.pct / 100.0,
                                      color: ModelTier(modelID: m.model).accent)
                                    .frame(width: 120, height: 4)
                                Spacer()
                                Text(fmtCost(m.cost)).font(.system(size: 11, weight: .semibold))
                                    .monospacedDigit()
                                Text(fmtTokens(m.tokens)).font(.system(size: 9))
                                    .foregroundStyle(.secondary)
                                    .frame(width: 54, alignment: .trailing)
                            }
                        }
                    }
                }
                .padding(6)
            }

            GroupBox("Last 7 days") {
                if let series = u?.series, series.contains(where: { $0.tokens > 0 }) {
                    Chart(series) { d in
                        BarMark(x: .value("day", String(d.day.suffix(5))),
                                y: .value("tokens", d.tokens))
                            .foregroundStyle(Color.accentColor.opacity(0.8))
                    }
                    .frame(height: 120)
                    .padding(6)
                } else {
                    Text("no local usage recorded yet")
                        .font(.system(size: 11)).foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity, alignment: .center).padding(12)
                }
            }
        }
    }
    @ViewBuilder func planMeter(_ label: String, _ b: GPlanBucket?) -> some View {
        if let b = b, let pct = b.pct {
            VStack(alignment: .leading, spacing: 3) {
                HStack {
                    Text(label).font(.system(size: 12))
                    Spacer()
                    Text("\(pct)%").font(.system(size: 13, weight: .bold))
                        .monospacedDigit().foregroundStyle(levelColor(pct))
                        .contentTransition(.numericText())
                    if let r = b.resetDisplay { Text("resets \(r)").font(.system(size: 9))
                        .foregroundStyle(.tertiary) }
                }
                Meter(fraction: Double(pct) / 100.0, color: levelColor(pct))
            }
        }
    }
    func stat(_ label: String, _ cost: Double?) -> some View {
        VStack(spacing: 2) {
            Text(fmtCost(cost ?? 0)).font(.system(size: 16, weight: .bold))
                .monospacedDigit().contentTransition(.numericText())
            Text(label).font(.system(size: 9)).foregroundStyle(.secondary)
        }.frame(maxWidth: .infinity)
    }
}

// --------------------------------------------------------------------------- //
// Agents — every session in full: collisions, live status, what happened.
// --------------------------------------------------------------------------- //
struct AgentsTab: View {
    @ObservedObject var model: TowerModel
    var body: some View {
        let sessions = model.agentSessions
        let events = Array((model.state?.agents?.events ?? []).suffix(20).reversed())
        VStack(alignment: .leading, spacing: 14) {
            if model.state?.agents == nil {
                EmptyState(anyResting: false)
            } else {
                ForEach(model.collisions) { c in CollisionBanner(collision: c) }

                GroupBox("Agents — \(sessions.count) session\(sessions.count == 1 ? "" : "s")") {
                    if sessions.isEmpty {
                        EmptyState(anyResting: false)
                    } else {
                        VStack(spacing: 2) {
                            ForEach(sessions) { s in AgentTableRow(model: model, session: s) }
                        }
                        .padding(4)
                    }
                }

                GroupBox("While you were away") {
                    if events.isEmpty {
                        Text("no state changes yet")
                            .font(.system(size: 11)).foregroundStyle(.secondary)
                            .frame(maxWidth: .infinity, alignment: .center).padding(10)
                    } else {
                        VStack(spacing: 3) {
                            ForEach(Array(events.enumerated()), id: \.offset) { _, e in
                                HStack(spacing: 8) {
                                    Text(e.t.map { agoString(sinceEpoch: $0) + " ago" } ?? "")
                                        .font(.system(size: 10, design: .monospaced))
                                        .foregroundStyle(.tertiary)
                                        .frame(width: 60, alignment: .leading)
                                    Text(project(e.session_id))
                                        .font(.system(size: 11, weight: .medium))
                                    Image(systemName: "arrow.right").font(.system(size: 8))
                                        .foregroundStyle(.tertiary)
                                    Text(AgentStatus(raw: e.to).phrase)
                                        .font(.system(size: 11))
                                        .foregroundStyle(AgentStatus(raw: e.to).color)
                                    Spacer()
                                }
                            }
                        }
                        .padding(6)
                    }
                }
            }
        }
    }
    func project(_ sid: String?) -> String {
        model.agentSessions.first { $0.session_id == sid }?.project_name ?? "agent"
    }
}

struct AgentTableRow: View {
    @ObservedObject var model: TowerModel
    let session: GAgentSession
    var body: some View {
        let st = AgentStatus(raw: session.status)
        let tier = ModelTier(family: session.model_family)
        HStack(spacing: 10) {
            ModelGlyphView(tier: tier, size: 22)
            VStack(alignment: .leading, spacing: 1) {
                HStack(spacing: 5) {
                    Text(session.project_name ?? "agent")
                        .font(.system(size: 12, weight: .medium))
                    Text(tier.display).font(.system(size: 9)).foregroundStyle(tier.accent)
                    if session.kind == "background" {
                        Text("bg").font(.system(size: 8, weight: .semibold))
                            .padding(.horizontal, 4).padding(.vertical, 1)
                            .background(Color.secondary.opacity(0.15), in: Capsule())
                            .foregroundStyle(.secondary)
                    }
                }
                Text(session.title ?? session.activity ?? session.last_prompt ?? "")
                    .font(.system(size: 10)).foregroundStyle(.secondary).lineLimit(1)
            }
            Spacer()
            if let t = session.ticks {
                Text("\(t.tools_done ?? 0) ✓ · \(t.files ?? 0) files"
                     + ((t.errors ?? 0) > 0 ? " · \(t.errors!) ✗" : ""))
                    .font(.system(size: 10)).monospacedDigit().foregroundStyle(.tertiary)
            }
            HStack(spacing: 4) {
                Image(systemName: st.symbol).font(.system(size: 10, weight: .semibold))
                Text(st.phrase).font(.system(size: 10, weight: .medium))
            }
            .foregroundStyle(st.color)
            .frame(width: 130, alignment: .leading)
        }
        .padding(.vertical, 4)
        .contentShape(Rectangle())
        .onTapGesture {
            if session.focusable == true {
                model.send(["cmd": "focus", "session_id": session.id])
            } else {
                let pb = NSPasteboard.general
                pb.clearContents()
                pb.setString("claude --resume \(session.id)", forType: .string)
            }
        }
    }
}

// --------------------------------------------------------------------------- //
// Settings
// --------------------------------------------------------------------------- //
struct SettingsTab: View {
    @ObservedObject var model: TowerModel
    @AppStorage("menubarMode") var mode = "session"
    @AppStorage("warnAt") var warn = 60
    @AppStorage("dangerAt") var danger = 85
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            GroupBox("Menu bar") {
                VStack(spacing: 8) {
                    row("Shows") {
                        Picker("", selection: $mode) {
                            Text("Icon").tag("off")
                            Text("Session %").tag("session")
                            Text("Week %").tag("week")
                        }
                        .pickerStyle(.segmented).labelsHidden().fixedSize()
                        .onChange(of: mode) { (NSApp.delegate as? AppDelegate)?.updateIcon() }
                    }
                    row("Yellow at") {
                        Stepper("\(warn)%", value: $warn, in: 10...95, step: 5).fixedSize()
                            .onChange(of: warn) { (NSApp.delegate as? AppDelegate)?.updateIcon() }
                    }
                    row("Red at") {
                        Stepper("\(danger)%", value: $danger, in: 20...100, step: 5).fixedSize()
                            .onChange(of: danger) { (NSApp.delegate as? AppDelegate)?.updateIcon() }
                    }
                }.padding(6)
            }
            GroupBox("Plan") {
                VStack(alignment: .leading, spacing: 8) {
                    row("Live plan limits") {
                        Toggle("", isOn: Binding(
                            get: { model.state?.settings?.plan_enabled ?? true },
                            set: { model.send(["cmd": "planfetch", "on": $0]) }))
                            .labelsHidden().toggleStyle(.switch).controlSize(.small)
                    }
                    Text("On reads real limits via a sandboxed `claude -p /usage` — no shell profile, no MCP, so it can't trigger Photos/Music prompts. Off keeps just the local estimate.")
                        .font(.system(size: 10)).foregroundStyle(.secondary)
                }.padding(6)
            }
            GroupBox("Guard") {
                VStack(spacing: 8) {
                    row("Country") {
                        Menu {
                            ForEach(COUNTRIES, id: \.cc) { c in
                                Button("\(flag(c.cc)) \(c.name)") {
                                    model.send(["cmd": "country", "cc": c.cc])
                                }
                            }
                        } label: {
                            Text("\(flag(model.state?.guardInfo?.target_cc)) \(model.state?.guardInfo?.target_cc ?? "US")")
                        }.fixedSize()
                    }
                    HStack {
                        Button("Re-check location") { model.send(["cmd": "recheck"]) }
                        Button("Refresh plan") { model.send(["cmd": "refreshplan"]) }
                        Spacer()
                        Button("Reset to defaults…") {
                            let a = NSAlert()
                            a.messageText = "Reset Tower to defaults?"
                            a.informativeText = "Removes routing from settings.json and disables keep-awake."
                            a.addButton(withTitle: "Reset")
                            a.addButton(withTitle: "Cancel")
                            if a.runModal() == .alertFirstButtonReturn {
                                model.send(["cmd": "reset"])
                            }
                        }
                    }
                }.padding(6)
            }
            HStack(spacing: 6) {
                Image(systemName: "gearshape.2").font(.system(size: 9)).foregroundStyle(.tertiary)
                Text("Tower \(model.state?.version ?? "—") · guard PID \(model.state?.procs?.daemon_pid.map(String.init) ?? "—")")
                    .font(.system(size: 10, design: .monospaced)).foregroundStyle(.tertiary)
            }
        }
    }
    @ViewBuilder func row<T: View>(_ t: String, @ViewBuilder _ trailing: () -> T) -> some View {
        HStack {
            Text(t).font(.system(size: 12)).foregroundStyle(.secondary)
            Spacer()
            trailing()
        }
    }
}
