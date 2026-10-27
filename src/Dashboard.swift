// Tower — the dashboard window: everything that doesn't belong in a glance.
//
// A native macOS window, not a web page in a frame: a source-list sidebar
// (live badges, and the guard riding at its foot), a unified toolbar bridged
// from SwiftUI that carries each page's title, live subtitle and actions, and
// pages built from one quiet panel vocabulary (Panel · StatTile · RingGauge).
// Five pages: Overview (the guard + the floor at a glance), Agents (Mail-style
// master–detail), Network (the weather station), Usage (the feed bill),
// Settings (a grouped form, System Settings style).
//
// A big window isn't a stretched small one: past `wide` the pages go to
// columns and reveal more; past `vast` the overview splits in three. Content is
// capped and centered so an ultra-wide window never strings a row across a
// room. The design system still governs (DESIGN.md): the mark is the state,
// motion = state change, one loudest thing — so only one radar moves at a time
// (the sidebar's stills while the Overview hero is on screen).

import AppKit
import SwiftUI
import Charts

enum DashboardTab: String, CaseIterable, Identifiable {
    case overview, agents, network, usage, settings
    var id: String { rawValue }
    var title: String {
        switch self {
        case .overview: return "Overview"; case .agents: return "Agents"
        case .network: return "Network"; case .usage: return "Usage"
        case .settings: return "Settings"
        }
    }
    var symbol: String {
        switch self {
        case .overview: return "square.grid.2x2"
        case .agents:   return "dot.radiowaves.left.and.right"
        case .network:  return "wifi"
        case .usage:    return "gauge.with.dots.needle.33percent"
        case .settings: return "gearshape"
        }
    }
}

final class DashboardWindowController: NSObject, NSWindowDelegate {
    private var window: NSWindow?
    private let model: TowerModel
    private let selected = SelectedTab()

    init(model: TowerModel) { self.model = model }

    func open(tab: DashboardTab) {
        selected.tab = tab
        if window == nil {
            let host = NSHostingController(
                rootView: DashboardView(model: model, selected: selected))
            // SwiftUI owns the window's toolbar and title: each page's
            // .navigationTitle / .toolbar land in a real unified NSToolbar.
            host.sceneBridgingOptions = [.toolbars, .title]
            host.sizingOptions = [.minSize]
            let w = NSWindow(
                contentRect: NSRect(x: 0, y: 0, width: 940, height: 620),
                styleMask: [.titled, .closable, .miniaturizable, .resizable,
                            .fullSizeContentView],
                backing: .buffered, defer: false)
            w.contentViewController = host
            w.title = "Tower"
            w.toolbarStyle = .unified
            w.isReleasedWhenClosed = false
            w.minSize = NSSize(width: 720, height: 500)
            w.setContentSize(NSSize(width: 1120, height: 740))
            w.center()
            w.setFrameAutosaveName("TowerDashboard.v2")   // reopen where you left it
            w.delegate = self
            window = w
        }
        setVisible(true)            // publish before ordering front: no stale frame
        NSApp.activate(ignoringOtherApps: true)
        window?.makeKeyAndOrderFront(nil)
    }

    // The window outlives a close (isReleasedWhenClosed = false), so without these
    // a closed, minimized or fully covered dashboard kept re-rendering every poll.
    func windowDidChangeOcclusionState(_ notification: Notification) {
        guard let w = window else { return }
        setVisible(w.isVisible && w.occlusionState.contains(.visible))
    }

    func windowWillClose(_ notification: Notification) { setVisible(false) }

    private func setVisible(_ on: Bool) {
        guard model.dashboardVisible != on else { return }
        if on { model.reveal { model.dashboardVisible = true } }
        else { model.dashboardVisible = false }
    }
}

/// Navigation state: the page, and the agent the Agents page has picked (so a
/// row on the Overview can jump straight to that agent's inspector).
final class SelectedTab: ObservableObject {
    @Published var tab: DashboardTab = .overview
    @Published var session: String?

    func show(_ tab: DashboardTab, session: String? = nil) {
        if let session { self.session = session }
        self.tab = tab
    }
}

struct DashboardView: View {
    @ObservedObject var model: TowerModel
    @ObservedObject var selected: SelectedTab
    /// The sidebar folds to an icon rail; it never disappears.
    @AppStorage("dash.sidebarRail") private var rail = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        // Visibility is pinned to .all: anything that would hide the sidebar
        // — the toggle, ⌃⌘S, dragging the divider shut — folds it to the rail
        // instead, and the same gestures unfold it.
        NavigationSplitView(columnVisibility: Binding(
            get: { .all },
            set: { v in if v != .all { setRail(!rail) } })) {
            DashSidebar(model: model, selected: selected, rail: rail)
                .background(SidebarWidthPin(rail: rail, animated: !reduceMotion))
                .toolbar(removing: .sidebarToggle)
                // Read once, when the split view is built; SidebarWidthPin
                // carries every later fold. Must stay the outermost modifier.
                .navigationSplitViewColumnWidth(min: rail ? DashSidebar.railWidth : 200,
                                                ideal: rail ? DashSidebar.railWidth : 214,
                                                max: rail ? DashSidebar.railWidth : 270)
        } detail: {
            DashDetail(model: model, selected: selected)
                .toolbar {
                    ToolbarItem(placement: .navigation) {
                        Button { setRail(!rail) } label: {
                            Label(rail ? "Expand Sidebar" : "Collapse Sidebar",
                                  systemImage: "sidebar.left")
                        }
                        .help(rail ? "Show the sidebar's labels" : "Fold the sidebar to icons")
                    }
                }
        }
        .environment(\.surfaceVisible, model.dashboardVisible)
        .tint(TowerDesign.ink)
        .toggleStyle(.tower)
        .dangerAlerts(model)
    }

    private func setRail(_ on: Bool) {
        withAnimation(.tower(TowerDesign.Motion.settle, reduced: reduceMotion)) { rail = on }
    }
}

/// Folds and unfolds the sidebar column. SwiftUI applies
/// `navigationSplitViewColumnWidth` only when the split view is first built,
/// so a later change has to reach the split item itself: pin its thickness
/// and move the divider (animated unless Reduce Motion).
struct SidebarWidthPin: NSViewRepresentable {
    let rail: Bool
    let animated: Bool

    final class Probe: NSView { var applied: Bool? }

    func makeNSView(context: Context) -> Probe { Probe() }

    func updateNSView(_ probe: Probe, context: Context) {
        guard probe.applied != rail else { return }
        // On the next turn: the probe needs to be in the window's hierarchy.
        DispatchQueue.main.async { apply(probe) }
    }

    private func apply(_ probe: Probe) {
        var v: NSView? = probe.superview
        while let cur = v, !(cur is NSSplitView) { v = cur.superview }
        guard let split = v as? NSSplitView,
              let item = (split.delegate as? NSSplitViewController)?.splitViewItems.first
        else { return }
        let first = probe.applied == nil
        probe.applied = rail
        let (lo, hi): (CGFloat, CGFloat) = rail ? (DashSidebar.railWidth, DashSidebar.railWidth) : (200, 270)
        let target = rail ? DashSidebar.railWidth : 214
        if first && abs((split.arrangedSubviews.first?.frame.width ?? 0) - target) < 1 { return }
        // Widen the range before moving, so neither limit blocks the move.
        item.minimumThickness = min(lo, item.minimumThickness)
        item.maximumThickness = max(hi, item.maximumThickness)
        let finish = {
            item.minimumThickness = lo
            item.maximumThickness = hi
        }
        if animated && !first {
            NSAnimationContext.runAnimationGroup({ ctx in
                ctx.duration = 0.28
                ctx.timingFunction = CAMediaTimingFunction(name: .easeInEaseOut)
                ctx.allowsImplicitAnimation = true
                split.setPosition(target, ofDividerAt: 0)
                split.layoutSubtreeIfNeeded()
            }, completionHandler: finish)
        } else {
            split.setPosition(target, ofDividerAt: 0)
            finish()
        }
    }
}

/// "Open Claude" in the toolbar: Desktop and claude.ai through the guard, on
/// every page. Desktop running unguarded marks the button amber — the one gap
/// this menu exists to close.
struct ClaudeAppsMenu: View {
    @ObservedObject var model: TowerModel

    var body: some View {
        let apps = model.state?.apps
        Menu {
            if let d = apps?.desktop, d.installed == true {
                Button { ClaudeLaunch.desktop(model) } label: {
                    Label(d.running == true && d.guarded != true
                          ? "Relaunch Claude Desktop Guarded" : "Claude Desktop",
                          systemImage: "macwindow")
                    Text(ClaudeLaunch.desktopLine(d))
                }
            }
            if let w = apps?.web, w.available == true {
                Button { ClaudeLaunch.web(model) } label: {
                    Label("Claude on the Web", systemImage: "globe")
                    Text(ClaudeLaunch.webLine(w))
                }
            }
            Divider()
            Text("Opened here, they go through the guard. Tower doesn't see their chats.")
        } label: {
            Label("Open Claude", systemImage: model.desktopGap
                  ? "exclamationmark.triangle" : "macwindow.on.rectangle")
        }
        .foregroundStyle(model.desktopGap ? Color(nsColor: .systemOrange) : Color.primary)
        .help(model.desktopGap ? "Claude Desktop is running without the guard"
                               : "Open Claude Desktop or claude.ai through the guard")
    }
}

// --------------------------------------------------------------------------- //
// Layout classes, measured on the detail column (the sidebar excluded).
// --------------------------------------------------------------------------- //
struct DashLayout {
    static let wide: CGFloat = 820
    static let vast: CGFloat = 1240
    var width: CGFloat = 900
    var height: CGFloat = 600
    var isWide: Bool { width >= Self.wide }
    var isVast: Bool { width >= Self.vast }
}

private struct DashLayoutKey: EnvironmentKey { static let defaultValue = DashLayout() }
extension EnvironmentValues {
    var dashLayout: DashLayout {
        get { self[DashLayoutKey.self] }
        set { self[DashLayoutKey.self] = newValue }
    }
}

// --------------------------------------------------------------------------- //
// Sidebar — the source list. Agents carries the needs-you count (the only
// number Tower ever badges); the guard sits at the foot, always in view.
// --------------------------------------------------------------------------- //
struct DashSidebar: View {
    @ObservedObject var model: TowerModel
    @ObservedObject var selected: SelectedTab
    /// Icons only — the folded sidebar. Wide enough to clear the traffic lights.
    var rail = false
    static let railWidth: CGFloat = 78

    var body: some View {
        // Our own items rather than List selection: every row is a real button
        // (always clickable, ⌘1–⌘5), the selection is Tower's white ink — not
        // the system blue — and icons stay monochrome.
        ScrollView {
            VStack(alignment: .leading, spacing: 2) {
                ForEach(Array([DashboardTab.overview, .agents, .network, .usage].enumerated()),
                        id: \.element) { i, tab in
                    SidebarItem(tab: tab, selected: selected.tab == tab,
                                badge: tab == .agents ? model.urgentCount : 0,
                                key: KeyEquivalent(Character("\(i + 1)")), rail: rail) { selected.show(tab) }
                }
                Divider().padding(.vertical, 8).padding(.horizontal, 6)
                SidebarItem(tab: .settings, selected: selected.tab == .settings,
                            badge: 0, key: "5", rail: rail) { selected.show(.settings) }
            }
            .padding(.horizontal, rail ? 12 : 10).padding(.top, 6)
        }
        .scrollBounceBehavior(.basedOnSize)
        .safeAreaInset(edge: .bottom, spacing: 0) {
            SidebarGuardFoot(model: model, still: selected.tab == .overview, rail: rail) {
                selected.show(.overview)
            }
        }
    }
}

struct SidebarItem: View {
    let tab: DashboardTab
    let selected: Bool
    let badge: Int
    let key: KeyEquivalent
    var rail = false
    let action: () -> Void
    @State private var hovering = false
    @State private var pressed = false

    var body: some View {
        Button(action: action) {
            Group {
                if rail {
                    // The folded rail: the symbol alone, its badge worn on the
                    // corner — the title moves to the tooltip.
                    icon(size: 15)
                        .frame(maxWidth: .infinity)
                        .overlay(alignment: .topTrailing) {
                            if badge > 0 { badgeView.offset(x: 2, y: -7) }
                        }
                        .frame(height: 38)
                } else {
                    HStack(spacing: 10) {
                        icon(size: 13).frame(width: 20)
                        Text(tab.title)
                            .font(.system(size: 13, weight: selected ? .semibold : .regular))
                            .foregroundStyle(.primary)
                            .lineLimit(1)
                        Spacer(minLength: 4)
                        if badge > 0 { badgeView }
                    }
                    .padding(.horizontal, 10).frame(height: 32)
                }
            }
            .background(RoundedRectangle(cornerRadius: 8, style: .continuous)
                .fill(Color.primary.opacity(selected ? 0.11 : hovering ? 0.05 : 0)))
            .scaleEffect(pressed ? 0.98 : 1)
            .contentShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
        }
        .buttonStyle(PressReporting(pressed: $pressed))
        .keyboardShortcut(key, modifiers: .command)
        .onHover { h in withAnimation(.easeOut(duration: 0.12)) { hovering = h } }
        .animation(.spring(response: 0.25, dampingFraction: 0.75), value: pressed)
        .animation(.easeOut(duration: 0.15), value: selected)
        .accessibilityAddTraits(selected ? .isSelected : [])
        .accessibilityLabel(tab.title)
        .help("\(tab.title)  ⌘\(String(key.character))")
    }

    private func icon(size: CGFloat) -> some View {
        Image(systemName: tab.symbol)
            .font(.system(size: size, weight: selected ? .semibold : .regular))
            .foregroundStyle(selected ? AnyShapeStyle(.primary) : AnyShapeStyle(.secondary))
    }

    private var badgeView: some View {
        Text("\(badge)")
            .font(.system(size: 10, weight: .bold)).monospacedDigit()
            .foregroundStyle(.white)
            .padding(.horizontal, 5).frame(minWidth: 16, minHeight: 16)
            .background(Capsule().fill(Color(nsColor: .systemOrange)))
            .contentTransition(.numericText())
    }
}

/// The one filled button: Tower's ink with a dark label — white-on-dark is the
/// primary, never the system blue.
struct InkButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var enabled
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 12, weight: .semibold))
            .foregroundStyle(TowerDesign.onInk)
            .padding(.horizontal, 12).frame(height: 26)
            .background(Capsule(style: .continuous).fill(TowerDesign.ink))
            .opacity(enabled ? (configuration.isPressed ? 0.8 : 1) : 0.4)
            .scaleEffect(configuration.isPressed ? 0.97 : 1)
            .animation(.spring(response: 0.25, dampingFraction: 0.75), value: configuration.isPressed)
    }
}

/// The guard, worn at the foot of the sidebar: the radar, the verdict, where.
/// Still while the Overview's hero radar is on screen — one moving mark at a time.
struct SidebarGuardFoot: View {
    @ObservedObject var model: TowerModel
    let still: Bool
    var rail = false
    let open: () -> Void
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var hovering = false

    var body: some View {
        let st = model.status
        Button(action: open) {
            HStack(spacing: 10) {
                TowerRadar(state: model.radarState, size: 28, awake: model.awakeGlow,
                           animated: !still)
                    .frame(width: 28, height: 28)
                    .frame(maxWidth: rail ? .infinity : nil)
                if !rail {
                VStack(alignment: .leading, spacing: 1) {
                    Text(st.title)
                        .font(.system(size: 12, weight: .semibold))
                        .lineLimit(1)
                        .contentTransition(.opacity)
                    if model.retryPending {
                        Text("Reconnecting Claude…")
                            .font(.system(size: 11)).foregroundStyle(st.swiftUIColor)
                            .lineLimit(1)
                            .shimmer(!reduceMotion)
                    } else {
                        Text(model.whereLine)
                            .font(.system(size: 11)).foregroundStyle(.secondary)
                            .lineLimit(1)
                    }
                }
                Spacer(minLength: 0)
                }
            }
            .padding(.horizontal, rail ? 0 : 10).padding(.vertical, 9)
            .background(RoundedRectangle(cornerRadius: 10, style: .continuous)
                .fill(Color.primary.opacity(hovering ? 0.08 : 0.05)))
            .contentShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
        }
        .buttonStyle(.plain)
        .onHover { hovering = $0 }
        .padding(rail ? 12 : 10)
        .animation(.tower(TowerDesign.Motion.settle, reduced: reduceMotion), value: st.title)
        .help(rail ? "\(st.title) — \(model.whereLine)" : "Guard status — open the Overview")
    }
}

// --------------------------------------------------------------------------- //
// Detail — the page, its toolbar title / live subtitle, and its actions.
// --------------------------------------------------------------------------- //
struct DashDetail: View {
    @ObservedObject var model: TowerModel
    @ObservedObject var selected: SelectedTab

    var body: some View {
        GeometryReader { geo in
            page
                .environment(\.dashLayout, DashLayout(width: geo.size.width, height: geo.size.height))
        }
        .navigationTitle(selected.tab.title)
        .navigationSubtitle(subtitle)
        .toolbar {
            ToolbarItemGroup(placement: .primaryAction) { actions }
        }
    }

    @ViewBuilder private var page: some View {
        switch selected.tab {
        case .overview: OverviewPage(model: model, selected: selected)
        case .agents:   AgentsPage(model: model, selected: selected)
        case .network:  DashPage { NetworkPage(model: model) }
        case .usage:    DashPage { UsagePage(model: model) }
        case .settings: SettingsPage(model: model)
        }
    }

    private var subtitle: String {
        switch selected.tab {
        case .overview: return model.status.title
        case .agents:   return model.floorSummary
        case .network:  return model.netVerdict.title
        case .usage:
            if let p = model.state?.plan, p.ok == true, let u = p.updated {
                return "Plan updated \(agoString(sinceEpoch: u)) ago"
            }
            return "Plan limits and local estimate"
        case .settings: return "Tower \(model.state?.version ?? "")"
        }
    }

    @ViewBuilder private var actions: some View {
        switch selected.tab {
        case .overview:
            Button { model.send(["cmd": "recheck"]) } label: {
                Label("Re-check Location", systemImage: "location.circle")
            }
            .help("Re-check your location now")
        case .network:
            let running = model.state?.net?.speedtest?.running == true
            Button { model.send(["cmd": "speedtest"]) } label: {
                Label("Run Speed Test", systemImage: "speedometer")
            }
            .disabled(running)
            .help("Measure download speed")
        case .usage:
            Button { model.send(["cmd": "refreshplan"]) } label: {
                Label("Refresh Plan", systemImage: "arrow.clockwise")
            }
            .disabled(model.state?.plan?.refreshing == true || model.usageGate != nil)
            .help("Re-read live plan limits")
        case .agents, .settings:
            EmptyView()
        }
        if model.hasClaudeApps { ClaudeAppsMenu(model: model) }
        Button {
            (NSApp.delegate as? AppDelegate)?.openTerminalDashboard()
        } label: {
            Label("Terminal Dashboard", systemImage: "terminal")
        }
        .help("Open the terminal dashboard")
    }
}

/// A scrolling page: padded, capped and centered so very wide windows stay legible.
struct DashPage<Content: View>: View {
    @ViewBuilder var content: Content
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) { content }
                .padding(.horizontal, 24).padding(.top, 18).padding(.bottom, 28)
                .frame(maxWidth: 1480, alignment: .topLeading)
                .frame(maxWidth: .infinity)
        }
    }
}

// --------------------------------------------------------------------------- //
// The panel vocabulary. One surface (a hairline-ruled, barely-filled rounded
// rect that reads right in light and dark), one header, one stat, one ring.
// --------------------------------------------------------------------------- //
enum DashStyle {
    static let radius: CGFloat = 12
    static let fill = Color.primary.opacity(0.035)
    static let fillHover = Color.primary.opacity(0.06)
    static let rule = Color.primary.opacity(0.075)
    static let gap: CGFloat = 16

    static func surface(_ fill: Color = DashStyle.fill) -> some View {
        RoundedRectangle(cornerRadius: radius, style: .continuous)
            .fill(fill)
            .overlay(RoundedRectangle(cornerRadius: radius, style: .continuous)
                .strokeBorder(rule, lineWidth: 0.5))
    }
}

private struct PanelFillKey: EnvironmentKey { static let defaultValue = false }
extension EnvironmentValues {
    /// Paired panels stretch to their row's height so both end on one line.
    var panelFill: Bool {
        get { self[PanelFillKey.self] }
        set { self[PanelFillKey.self] = newValue }
    }
}

struct Panel<Content: View, Accessory: View>: View {
    @Environment(\.panelFill) private var fill
    var title: String?
    var symbol: String?
    /// Flush content runs edge to edge (for rows that carry their own insets).
    var flush = false
    @ViewBuilder var content: Content
    @ViewBuilder var accessory: Accessory

    init(_ title: String? = nil, symbol: String? = nil, flush: Bool = false,
         @ViewBuilder content: () -> Content, @ViewBuilder accessory: () -> Accessory) {
        self.title = title; self.symbol = symbol; self.flush = flush
        self.content = content(); self.accessory = accessory()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if let title {
                HStack(spacing: 6) {
                    if let symbol {
                        Image(systemName: symbol)
                            .font(.system(size: 11, weight: .semibold))
                            .foregroundStyle(.secondary)
                    }
                    Text(title).font(.system(size: 13, weight: .semibold))
                    Spacer(minLength: 8)
                    accessory
                        .font(.system(size: 11))
                        .foregroundStyle(.secondary)
                }
                .padding(.horizontal, 16)
            }
            content
                .padding(.horizontal, flush ? 0 : 16)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(.vertical, 14)
        .frame(maxWidth: .infinity, maxHeight: fill ? .infinity : nil, alignment: .topLeading)
        .background(DashStyle.surface())
    }
}

extension Panel where Accessory == EmptyView {
    init(_ title: String? = nil, symbol: String? = nil, flush: Bool = false,
         @ViewBuilder content: () -> Content) {
        self.init(title, symbol: symbol, flush: flush, content: content, accessory: { EmptyView() })
    }
}

/// A number worth reading from across the room, with its label and one line of
/// context. Counters tick (numericText) — the dopamine layer, scaled up.
struct StatTile: View {
    let label: String
    let value: String
    var unit: String? = nil
    var detail: String? = nil
    var symbol: String? = nil
    var tint: Color = .primary
    var size: CGFloat = 26
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 5) {
                if let symbol {
                    Image(systemName: symbol).font(.system(size: 10, weight: .semibold))
                }
                Text(label).font(.system(size: 11, weight: .medium))
            }
            .foregroundStyle(.secondary)
            HStack(alignment: .firstTextBaseline, spacing: 3) {
                Text(value)
                    .font(.system(size: size, weight: .semibold, design: .rounded))
                    .monospacedDigit()
                    .foregroundStyle(tint)
                    .contentTransition(.numericText())
                if let unit {
                    Text(unit).font(.system(size: size * 0.46, weight: .medium, design: .rounded))
                        .foregroundStyle(.secondary)
                }
            }
            .lineLimit(1).minimumScaleFactor(0.7)
            if let detail {
                Text(detail).font(.system(size: 11)).foregroundStyle(.tertiary)
                    .lineLimit(1)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .animation(.tower(TowerDesign.Motion.settle, reduced: reduceMotion), value: value)
    }
}

/// Activity-ring style meter. The track is the tint at low opacity; the arc
/// settles on the spring (a fade under Reduce Motion).
struct RingGauge: View {
    let fraction: Double
    var tint: Color = TowerDesign.ink
    var lineWidth: CGFloat = 10
    /// A plan limit at 0% still shows its starting dot; a meter with nothing
    /// measured yet (the speed test) shows a bare track.
    var marksZero = true
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        let f = min(max(fraction, 0), 1)
        ZStack {
            Circle().stroke(tint.opacity(0.14), lineWidth: lineWidth)
            if f > 0 || marksZero { arc(f) }
        }
        .padding(lineWidth / 2)
        .animation(.tower(TowerDesign.Motion.settle, reduced: reduceMotion), value: f)
    }

    private func arc(_ f: Double) -> some View {
            Circle()
                .trim(from: 0, to: max(f, 0.004))
                .stroke(AngularGradient(colors: [tint.opacity(0.75), tint],
                                        center: .center,
                                        startAngle: .degrees(0),
                                        endAngle: .degrees(360 * max(f, 0.01))),
                        style: StrokeStyle(lineWidth: lineWidth, lineCap: .round))
                .rotationEffect(.degrees(-90))
    }
}

/// A label · trailing-control row inside a panel, System Settings style.
struct PanelRow<Trailing: View>: View {
    let title: String
    var symbol: String? = nil
    var detail: String? = nil
    @ViewBuilder var trailing: Trailing
    var body: some View {
        HStack(spacing: 10) {
            if let symbol {
                Image(systemName: symbol)
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(.secondary)
                    .frame(width: 18)
            }
            VStack(alignment: .leading, spacing: 1) {
                Text(title).font(.system(size: 13))
                if let detail {
                    Text(detail).font(.system(size: 11)).foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            Spacer(minLength: 10)
            trailing
        }
        .frame(minHeight: 28)
    }
}

/// A small, calm capsule label ("claude", "allowed", "bg").
struct Chip: View {
    let text: String
    var tint: Color = .secondary
    var body: some View {
        Text(text)
            .font(.system(size: 10, weight: .semibold))
            .padding(.horizontal, 7).frame(height: 18)
            .foregroundStyle(tint)
            .background(Capsule(style: .continuous).fill(tint.opacity(0.13)))
    }
}

/// Honest gate message — usage can't be read while the guard isn't passing,
/// and it says whether that's the connection or the location / VPN.
struct UsageGateNote: View {
    @ObservedObject var model: TowerModel
    var roomy = true
    var body: some View {
        UsagePaused(model: model).padding(.vertical, roomy ? 6 : 0)
    }
}

// --------------------------------------------------------------------------- //
// Model-derived copy shared by the pages (kept off the views so the sidebar,
// toolbar and panels can never word the same fact two ways).
// --------------------------------------------------------------------------- //
struct NetVerdict {
    let symbol: String
    let tint: Color
    let title: String
    let detail: String
    let healthy: Bool
}

extension TowerModel {
    /// "🇨🇦 Toronto, CA" — or what's stopping us knowing.
    var whereLine: String {
        let loc = state?.location
        if netStatus == .offline { return "Offline — location unknown" }
        guard let loc, loc.status == "OK" else { return "Locating…" }
        return "\(flag(loc.country_cc)) \(loc.city ?? "?"), \(loc.country_cc ?? "?")"
    }

    var targetCC: String { state?.guardInfo?.target_cc ?? state?.settings?.country ?? "US" }
    var targetName: String { COUNTRIES.first { $0.cc == targetCC }?.name ?? targetCC }

    /// The guard's state, as one honest sentence.
    var guardSentence: String {
        switch status {
        case .starting:  return "Starting the guard…"
        case .protected: return "Claude is fenced to \(flag(targetCC)) \(targetName), and the path to Anthropic is open."
        case .blocking:  return "You're outside \(targetName) — Claude requests are held, not failed, until you're back."
        case .unstable:  return "No usable path to Anthropic — requests are held and resume on their own."
        case .locating:  return "Confirming your location — requests are held until it's sure."
        case .unrouted:  return "Claude Code connects directly — there is no country guard."
        case .monitor:   return "Enforcement is off — Tower is watching, not blocking."
        }
    }

    /// "3 working · 1 needs you · 12 done today"
    var floorSummary: String {
        let w = workingAgents.count, n = needsYouCount
        let done = state?.agents?.summary?.done_today ?? 0
        let parts = [w > 0 ? "\(w) working" : nil,
                     n > 0 ? "\(n) need\(n == 1 ? "s" : "") you" : nil,
                     done > 0 ? "\(done) done today" : nil].compactMap { $0 }
        return parts.isEmpty ? "All quiet" : parts.joined(separator: " · ")
    }

    /// The net weather verdict — same wording as the popover's NetRow banner.
    var netVerdict: NetVerdict {
        let net = state?.net
        let orange = Color(nsColor: .systemOrange), red = Color(nsColor: .systemRed)
        switch netStatus {
        case .online:
            return NetVerdict(symbol: "wifi", tint: Color(nsColor: .systemGreen),
                              title: "Connection healthy",
                              detail: "Internet and the Anthropic API are both reachable",
                              healthy: true)
        case .degraded:
            switch net?.reason {
            case "dns":
                return NetVerdict(symbol: "wifi.exclamationmark", tint: orange,
                                  title: "DNS problem",
                                  detail: "Your resolver is failing — not Anthropic", healthy: false)
            case "api_slow":
                return NetVerdict(symbol: "clock.badge.exclamationmark", tint: orange,
                                  title: "Slow path to Anthropic",
                                  detail: "Handshake \(fmtMs(net?.api_ms)) — link is fine, replies may lag",
                                  healthy: false)
            default:
                return NetVerdict(symbol: "wifi.exclamationmark", tint: orange,
                                  title: "Internet is slow",
                                  detail: "Ping \(fmtMs(net?.internet_ms)) — expect Claude timeouts",
                                  healthy: false)
            }
        case .offline:
            return NetVerdict(symbol: "wifi.slash", tint: red, title: "Your internet is offline",
                              detail: "Claude errors are local — not Anthropic", healthy: false)
        case .apiIssue:
            return NetVerdict(symbol: "exclamationmark.icloud", tint: orange,
                              title: "Anthropic API unreachable",
                              detail: "Your internet is fine (\(fmtMs(net?.internet_ms)))", healthy: false)
        case .captive:
            return NetVerdict(symbol: "wifi.exclamationmark", tint: red, title: "Wi-Fi login required",
                              detail: "Open a browser to sign in to this network", healthy: false)
        case .checking, .unknown:
            return NetVerdict(symbol: "waveform.path.ecg", tint: .secondary,
                              title: "Measuring the connection…",
                              detail: "The first samples arrive in a few seconds", healthy: true)
        }
    }

    /// Route on is one tap; off is the double-confirmed danger path.
    func setRouting(_ on: Bool) {
        if on { send(["cmd": "route", "on": true]); return }
        requestDanger(
            "Turn off the guard?",
            "This removes routing from settings.json and Claude Code "
            + "connects DIRECTLY to the API — with no country guard at all.",
            confirm: "Turn off guard") { [weak self] in
            self?.send(["cmd": "route", "on": false]) }
    }

    func setEnforce(_ on: Bool) {
        if on { send(["cmd": "enforce", "on": true]); return }
        requestDanger(
            "Stop enforcing the guard?",
            "Claude will still route through the guard, but requests are NO "
            + "LONGER blocked when you're outside \(targetCC).",
            confirm: "Stop enforcing") { [weak self] in
            self?.send(["cmd": "enforce", "on": false]) }
    }

    /// Needs-you first, then working, then everyone else by recency.
    var sessionsOrdered: [GAgentSession] {
        let needs = needsYou, working = workingAgents
        let seen = Set((needs + working).map(\.id))
        let rest = agentSessions.filter { !seen.contains($0.id) }
            .sorted { ($0.last_activity ?? 0) > ($1.last_activity ?? 0) }
        return needs + working + rest
    }
}

/// A session's one line: the reason it failed, what it's waiting on, what it
/// produced, or what it's doing — never the stale prompt when there's news.
func sessionLine(_ s: GAgentSession) -> String {
    let st = AgentStatus(raw: s.status)
    switch st {
    case .failed: return s.activity.flatMap { $0.isEmpty ? nil : $0 } ?? "failed"
    case .pendingTool:
        if let p = s.pending_tool {
            return "Approve \(p.name ?? "tool")" + (p.detail.map { " · \($0)" } ?? "")
        }
        return "waiting for approval"
    case .asking: return s.activity ?? "asked you a question"
    case .done, .waitingInput: return s.result ?? s.title ?? st.phrase
    case .working: return s.activity ?? "thinking…"
    default: return s.title ?? s.last_prompt ?? st.phrase
    }
}

// --------------------------------------------------------------------------- //
// Overview — the guard, four numbers, the floor, and the station's instruments.
// --------------------------------------------------------------------------- //
struct OverviewPage: View {
    @ObservedObject var model: TowerModel
    @ObservedObject var selected: SelectedTab
    @Environment(\.dashLayout) private var layout

    // A glance sized to the window, never a page you scroll — and it grows
    // with the window: the guard, who's working, your limits and connection
    // at any size; the requests passing through, then the cost and the week,
    // as width and height make room. Panels that can use height (the agents,
    // the request log) absorb what's left, so every column ends together.
    var body: some View {
        if layout.width >= 700 && layout.height >= 500 {
            VStack(spacing: DashStyle.gap) {
                GuardHero(model: model)
                HStack(alignment: .top, spacing: DashStyle.gap) {
                    LiveFloorPanel(model: model, selected: selected, fill: true)
                        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
                    if layout.width >= 1180 {
                        VStack(spacing: DashStyle.gap) {
                            plan
                            EstimatePanel(model: model)
                            if layout.height >= 780 {
                                WeekPanel(model: model, height: 110, fill: true)
                            } else {
                                Spacer(minLength: 0)
                            }
                        }
                        .frame(width: 340)
                        VStack(spacing: DashStyle.gap) {
                            net
                            RequestsPanel(model: model, fill: true)
                        }
                        .frame(width: 340)
                    } else {
                        VStack(spacing: DashStyle.gap) {
                            plan
                            net
                            if layout.height >= 660 {
                                RequestsPanel(model: model, fill: true)
                            } else {
                                Spacer(minLength: 0)
                            }
                        }
                        .frame(width: layout.isWide ? 340 : 300)
                    }
                }
                .frame(maxHeight: .infinity)
            }
            .padding(.horizontal, 24).padding(.top, 18).padding(.bottom, 24)
            .frame(maxWidth: 1600, maxHeight: .infinity, alignment: .top)
            .frame(maxWidth: .infinity)
        } else {
            DashPage {
                GuardHero(model: model)
                LiveFloorPanel(model: model, selected: selected)
                plan
                NetGlancePanel(model: model) { selected.show(.network) }
            }
        }
    }

    private var plan: some View { PlanGlancePanel(model: model) { selected.show(.usage) } }
    private var net: some View {
        NetGlancePanel(model: model, chart: layout.height >= 640 ? 54 : 34) { selected.show(.network) }
    }
}

/// The requests passing through the guard, minimal: Claude's per-minute pulse
/// over the last quarter hour, what's passed and held, and the newest few —
/// held ones in amber (a hold is pending, never failed). Fills its column.
struct RequestsPanel: View {
    @ObservedObject var model: TowerModel
    var fill = false
    var body: some View {
        let g = model.state?.guardInfo
        let recent = Array((model.state?.recent ?? []).reversed())
        let amber = Color(nsColor: .systemOrange)
        Panel("Requests", symbol: "arrow.left.arrow.right", flush: true) {
            VStack(alignment: .leading, spacing: 10) {
                pulse(recent).padding(.horizontal, 16)
                if recent.isEmpty {
                    Text("Nothing through the guard yet")
                        .font(.system(size: 11)).foregroundStyle(.tertiary)
                        .padding(.horizontal, 16)
                } else if fill {
                    ScrollView { rows(recent) }.scrollBounceBehavior(.basedOnSize)
                } else {
                    rows(Array(recent.prefix(6)))
                }
            }
        } accessory: {
            if (g?.holding ?? 0) > 0 {
                Text("↻ \(g?.holding ?? 0) held now").foregroundStyle(amber)
            } else {
                Text("\(fmtCount(g?.allowed ?? 0)) passed"
                     + ((g?.blocked ?? 0) > 0 ? " · \(fmtCount(g?.blocked ?? 0)) held" : ""))
                    .monospacedDigit()
            }
        }
    }

    /// Claude requests per minute, the last 15 minutes — the newest bar in ink.
    private func pulse(_ events: [GEvent]) -> some View {
        let cal = Calendar.current
        let now = Date()
        let nowMin = cal.component(.hour, from: now) * 60 + cal.component(.minute, from: now)
        var bins = Array(repeating: 0, count: 15)
        for e in events where e.kind == "claude" {
            let p = (e.t ?? "").split(separator: ":").compactMap { Int($0) }
            guard p.count >= 2 else { continue }
            let age = (nowMin - (p[0] * 60 + p[1]) + 1440) % 1440
            if age < 15 { bins[14 - age] += 1 }
        }
        let peak = max(bins.max() ?? 0, 1)
        return HStack(alignment: .bottom, spacing: 12) {
            HStack(alignment: .bottom, spacing: 3) {
                ForEach(Array(bins.enumerated()), id: \.offset) { i, n in
                    RoundedRectangle(cornerRadius: 1.5, style: .continuous)
                        .fill(TowerDesign.ink.opacity(i == 14 ? 1 : n > 0 ? 0.45 : 0.12))
                        .frame(height: max(2, 22 * CGFloat(n) / CGFloat(peak)))
                }
            }
            .frame(height: 22, alignment: .bottom)
            VStack(alignment: .trailing, spacing: 0) {
                Text("\(bins[14])").font(.system(size: 15, weight: .semibold, design: .rounded))
                    .monospacedDigit().contentTransition(.numericText())
                Text("/min").font(.system(size: 10)).foregroundStyle(.tertiary)
            }
            .fixedSize()
        }
        .help("Claude requests per minute, last 15 minutes")
    }

    private func rows(_ events: [GEvent]) -> some View {
        VStack(spacing: 0) {
            ForEach(Array(events.enumerated()), id: \.offset) { _, e in
                let held = e.action == "blocked"
                HStack(spacing: 8) {
                    Circle().fill(held ? Color(nsColor: .systemOrange)
                                  : e.kind == "claude" ? TowerDesign.ink : Color.primary.opacity(0.25))
                        .frame(width: 5, height: 5)
                    Text(e.host ?? "?").font(.system(size: 11.5))
                        .foregroundStyle(e.kind == "claude" ? AnyShapeStyle(.primary) : AnyShapeStyle(.secondary))
                        .lineLimit(1).truncationMode(.middle)
                    Spacer(minLength: 6)
                    if held { Text("held").font(.system(size: 10, weight: .semibold))
                        .foregroundStyle(Color(nsColor: .systemOrange)) }
                    Text(e.t ?? "").font(TowerDesign.Font.mono(10)).foregroundStyle(.tertiary)
                }
                .padding(.horizontal, 16).frame(height: 22)
            }
        }
    }
}

func fmtCount(_ n: Int) -> String {
    let f = NumberFormatter(); f.numberStyle = .decimal
    return f.string(from: NSNumber(value: n)) ?? "\(n)"
}

/// The guard, large: the radar, the verdict, one honest sentence, where you
/// are — and the one primary control. Only a hold or danger tints the surface.
struct GuardHero: View {
    @ObservedObject var model: TowerModel
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.dashLayout) private var layout

    var body: some View {
        let st = model.status
        let routed = model.state?.routing?.installed ?? false
        let wash: Color? = (st == .protected || st == .monitor || st == .starting) ? nil : st.swiftUIColor
        Group {
            if layout.width < 600 {
                // Narrow: the mark, the verdict and the switch share one header
                // row; the sentence and where get the full width under it.
                VStack(alignment: .leading, spacing: 8) {
                    HStack(spacing: 12) {
                        TowerRadar(state: model.radarState, size: 38, awake: model.awakeGlow)
                            .frame(width: 38, height: 38)
                        Text(st.title)
                            .font(.system(size: 18, weight: .bold))
                            .lineLimit(1)
                            .contentTransition(.opacity)
                        Spacer(minLength: 8)
                        guardSwitch(routed, label: false)
                    }
                    sentence
                    locationLine
                }
            } else {
                HStack(alignment: .center, spacing: 16) {
                    TowerRadar(state: model.radarState, size: 52, awake: model.awakeGlow)
                        .frame(width: 52, height: 52)
                    VStack(alignment: .leading, spacing: 3) {
                        Text(st.title)
                            .font(.system(size: 20, weight: .bold))
                            .lineLimit(1)
                            .contentTransition(.opacity)
                        sentence
                        locationLine.padding(.top, 1)
                    }
                    Spacer(minLength: 16)
                    guardSwitch(routed, label: true)
                }
            }
        }
        .padding(.horizontal, layout.width < 600 ? 16 : 18).padding(.vertical, 14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background {
            ZStack {
                DashStyle.surface()
                if let wash {
                    RoundedRectangle(cornerRadius: DashStyle.radius, style: .continuous)
                        .fill(LinearGradient(colors: [wash.opacity(0.13), wash.opacity(0.02)],
                                             startPoint: .leading, endPoint: .trailing))
                }
            }
        }
        .animation(.tower(TowerDesign.Motion.settle, reduced: reduceMotion), value: st.title)
    }

    @ViewBuilder private var sentence: some View {
        if model.retryPending {
            Text("Reconnecting Claude…")
                .font(.system(size: 13, weight: .medium))
                .foregroundStyle(model.status.swiftUIColor)
                .shimmer(!reduceMotion)
        } else {
            Text(model.guardSentence)
                .font(.system(size: 13)).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    @ViewBuilder private func guardSwitch(_ routed: Bool, label: Bool) -> some View {
        let toggle = Toggle(isOn: Binding(get: { routed }, set: { model.setRouting($0) })) {
            Text("Guard").font(.system(size: 13, weight: .medium))
        }
        Group {
            if label { toggle } else { toggle.labelsHidden() }
        }
        .fixedSize()
        .help("Route Claude through the guard")
        .accessibilityLabel("Guard")
    }

    /// Where you are, on one line at any width: it sheds the ISP, then the IP,
    /// then the region before it would ever wrap.
    @ViewBuilder private var locationLine: some View {
        let loc = model.state?.location
        Group {
            if let loc, loc.status == "OK" {
                let city = [loc.city, loc.region].compactMap { $0 }.joined(separator: ", ")
                ViewThatFits(in: .horizontal) {
                    whereRow(loc, place: city, isp: loc.isp, ip: loc.ip)
                    whereRow(loc, place: city, isp: nil, ip: loc.ip)
                    whereRow(loc, place: city, isp: nil, ip: nil)
                    whereRow(loc, place: loc.city ?? city, isp: nil, ip: nil)
                }
            } else {
                HStack(spacing: 6) {
                    Image(systemName: "location").foregroundStyle(.tertiary)
                    Text(loc?.error ?? "Locating…").lineLimit(1)
                }
            }
        }
        .font(.system(size: 11))
        .foregroundStyle(.secondary)
    }

    private func whereRow(_ loc: GLocation, place: String, isp: String?, ip: String?) -> some View {
        HStack(spacing: 6) {
            Text(flag(loc.country_cc))
            Text(place)
            if let isp { dot; Text(isp) }
            if let ip {
                dot
                Text(ip).font(TowerDesign.Font.mono(11)).textSelection(.enabled)
            }
            if loc.in_target == false {
                Chip(text: "outside \(model.targetCC)", tint: Color(nsColor: .systemOrange))
            }
        }
        .lineLimit(1)
        .fixedSize()
    }
    private var dot: some View { Text("·").foregroundStyle(.quaternary) }
}

struct LiveFloorPanel: View {
    @ObservedObject var model: TowerModel
    @ObservedObject var selected: SelectedTab
    /// Fill the space it's given, scrolling its rows inside (the Overview).
    var fill = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        Panel("Live agents", symbol: "dot.radiowaves.left.and.right", flush: true) {
            if fill {
                ScrollView { rows }.scrollBounceBehavior(.basedOnSize)
            } else {
                rows
            }
        } accessory: {
            Text(model.floorSummary).monospacedDigit().contentTransition(.numericText())
        }
    }

    @ViewBuilder private var rows: some View {
        let needs = model.needsYou
        let working = model.workingAgents
        let resting = model.agentSessions.count - needs.count - working.count
            VStack(alignment: .leading, spacing: 2) {
                if model.unguardedCount > 0 {
                    GuardGapBanner(model: model, count: model.unguardedCount, unguarded: true)
                }
                ForEach(model.collisions) { c in CollisionBanner(collision: c) }
                if needs.isEmpty && working.isEmpty {
                    EmptyFloor(compact: true, anySessions: resting > 0)
                } else {
                    ForEach(needs) { s in row(s).towerRow() }
                    if !needs.isEmpty && !working.isEmpty {
                        Divider().padding(.horizontal, 16).padding(.vertical, 4)
                    }
                    ForEach(working) { s in row(s).towerRow() }
                }
                if resting > 0 {
                    Button { selected.show(.agents) } label: {
                        HStack(spacing: 6) {
                            Image(systemName: "zzz").font(.system(size: 10))
                            Text("\(resting) resting")
                            Image(systemName: "chevron.right").font(.system(size: 9, weight: .semibold))
                        }
                        .font(.system(size: 11)).foregroundStyle(.tertiary)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .padding(.horizontal, 16).padding(.top, 6)
                }
            }
            .padding(.horizontal, 6)
            .animation(.tower(TowerDesign.Motion.reorder, reduced: reduceMotion),
                       value: needs.map(\.id) + working.map(\.id))
    }

    private func row(_ s: GAgentSession) -> some View {
        SessionRow(model: model, session: s, selected: false, subagents: true) {
            if s.focusable == true {
                model.send(["cmd": "focus", "session_id": s.id])
            } else {
                selected.show(.agents, session: s.id)
            }
        }
    }
}

/// One agent, one row — the same row on the Overview floor and in the Agents
/// list: its living mark, name + model chip, its one line, and its time.
struct SessionRow: View {
    @ObservedObject var model: TowerModel
    let session: GAgentSession
    var selected: Bool
    var subagents = false
    let onTap: () -> Void
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.surfaceVisible) private var visible
    @State private var hovering = false

    var body: some View {
        let st = AgentStatus(raw: session.status)
        let tier = ModelTier(family: session.model_family)
        let tooling = st == .working && session.pending_tool != nil
        let subs = session.subagentsOrdered
        VStack(alignment: .leading, spacing: 3) {
            HStack(spacing: 10) {
                ModelGlyphView(tier: tier, working: st == .working, size: 26)
                    .opacity(st == .idle || st == .gone ? 0.5 : 1)
                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 6) {
                        Text(session.project_name ?? "agent")
                            .font(.system(size: 13, weight: .medium))
                            .foregroundStyle(st == .idle || st == .gone
                                             ? AnyShapeStyle(.secondary) : AnyShapeStyle(.primary))
                            .lineLimit(1)
                        ModelMeta(session: session)
                        if session.kind == "background" { Chip(text: "bg") }
                        UnguardedChip(model: model, session: session)
                        if session.health?.level == "warn" {
                            Image(systemName: "exclamationmark.triangle.fill")
                                .font(.system(size: 9))
                                .foregroundStyle(Color(nsColor: .systemYellow))
                                .help((session.health?.reasons ?? []).joined(separator: "\n"))
                        }
                        Spacer(minLength: 4)
                        if let t = session.ticks?.tools_done, t > 0, st == .working {
                            Text("\(t) tool\(t == 1 ? "" : "s")").font(TowerDesign.Font.counter)
                                .foregroundStyle(.tertiary)
                                .contentTransition(.numericText())
                        }
                        Text(st == .working && session.turn_at != nil
                             ? elapsedString(sinceEpoch: session.turn_at!)
                             : agoString(sinceEpoch: (st.needsYouRank != nil ? session.status_since
                                                    : session.last_activity) ?? Date().timeIntervalSince1970))
                            .font(.system(size: 11, weight: .medium)).monospacedDigit()
                            .foregroundStyle(.secondary)
                    }
                    HStack(spacing: 5) {
                        if st.needsYouRank != nil || st == .paused {
                            Image(systemName: st.symbol)
                                .font(.system(size: 10, weight: .semibold))
                                .foregroundStyle(st.color)
                        } else if tooling && visible {
                            ProgressView().controlSize(.mini)
                        }
                        Text(sessionLine(session))
                            .font(.system(size: 11))
                            .foregroundStyle(st == .failed ? AnyShapeStyle(st.color) : AnyShapeStyle(.secondary))
                            .lineLimit(1).truncationMode(.tail)
                            .shimmer(tooling && !reduceMotion)
                    }
                }
            }
            if subagents && !subs.isEmpty {
                SubagentTree(subagents: subs, rail: 13, limit: 3)
            }
        }
        .padding(.horizontal, 10).padding(.vertical, 7)
        .background(RoundedRectangle(cornerRadius: 8, style: .continuous)
            .fill(selected ? TowerDesign.ink.opacity(0.17)
                  : Color.primary.opacity(hovering ? 0.045 : 0)))
        .contentShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
        .onHover { hovering = $0 }
        .onTapGesture(perform: onTap)
        .contextMenu { SessionMenu(model: model, session: session) }
        .animation(.tower(TowerDesign.Motion.settle, reduced: reduceMotion), value: subs.map(\.id))
    }
}

/// The native right-click menu every agent row carries.
struct SessionMenu: View {
    @ObservedObject var model: TowerModel
    let session: GAgentSession
    var body: some View {
        if session.focusable == true {
            Button("Show Terminal") { model.send(["cmd": "focus", "session_id": session.id]) }
        }
        if AgentStatus(raw: session.status).needsYouRank != nil {
            Divider()
            Button("Dismiss") { model.send(["cmd": "dismiss", "session_id": session.id]) }
        }
    }
}

/// No agents — a quiet, still scope.
struct EmptyFloor: View {
    var compact = false
    var anySessions = false
    var body: some View {
        VStack(spacing: compact ? 6 : 10) {
            TowerRadar(state: .clear, size: compact ? 34 : 60, color: .secondary, animated: false)
                .frame(width: compact ? 34 : 60, height: compact ? 34 : 60)
                .opacity(0.55)
            Text(anySessions ? "No agent is working right now" : "No Claude Code sessions yet")
                .font(.system(size: compact ? 12 : 15, weight: compact ? .regular : .semibold))
                .foregroundStyle(compact ? .secondary : .primary)
            Text("Run `claude` in any terminal — it shows up here the moment it starts.")
                .font(.system(size: 11)).foregroundStyle(.tertiary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, compact ? 18 : 60)
    }
}

/// State changes, newest first — all sessions, or one.
struct TimelineRows: View {
    @ObservedObject var model: TowerModel
    let sessionID: String?
    var limit = 20
    var body: some View {
        let events = Array((model.state?.agents?.events ?? [])
            .filter { sessionID == nil || $0.session_id == sessionID }
            .suffix(limit).reversed())
        if events.isEmpty {
            Text("No state changes yet")
                .font(.system(size: 11)).foregroundStyle(.tertiary)
                .frame(maxWidth: .infinity, alignment: .center).padding(.vertical, 8)
        } else {
            VStack(alignment: .leading, spacing: 0) {
                ForEach(Array(events.enumerated()), id: \.offset) { i, e in
                    let to = AgentStatus(raw: e.to)
                    HStack(spacing: 10) {
                        // A thin spine with one node per change.
                        ZStack {
                            Rectangle().fill(Color.primary.opacity(0.08)).frame(width: 1)
                                .opacity(i == events.count - 1 ? 0 : 1)
                                .offset(y: 11)
                            Circle().fill(to.needsYouRank != nil ? to.color : Color.secondary.opacity(0.5))
                                .frame(width: 7, height: 7)
                        }
                        .frame(width: 10, height: 22)
                        if sessionID == nil {
                            Text(project(e.session_id))
                                .font(.system(size: 12, weight: .medium)).lineLimit(1)
                        }
                        Text(to.phrase)
                            .font(.system(size: 12))
                            .foregroundStyle(to.needsYouRank != nil ? AnyShapeStyle(to.color)
                                                                    : AnyShapeStyle(.secondary))
                        Spacer(minLength: 6)
                        Text(e.t.map { agoString(sinceEpoch: $0) + " ago" } ?? "")
                            .font(TowerDesign.Font.counter).foregroundStyle(.tertiary)
                    }
                }
            }
        }
    }
    func project(_ sid: String?) -> String {
        model.agentSessions.first { $0.session_id == sid }?.project_name ?? "agent"
    }
}

struct NetGlancePanel: View {
    @ObservedObject var model: TowerModel
    var chart: CGFloat = 54
    let open: () -> Void
    var body: some View {
        let net = model.state?.net
        let v = model.netVerdict
        Panel("Network", symbol: "wifi") {
            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 8) {
                    Image(systemName: v.symbol).foregroundStyle(v.tint)
                        .font(.system(size: 12, weight: .semibold))
                    Text(v.title).font(.system(size: 12, weight: .medium))
                    Spacer()
                }
                HStack(spacing: 12) {
                    StatTile(label: "Internet", value: net?.internet_ms.map { "\(Int($0))" } ?? "—",
                             unit: "ms", size: 20)
                    StatTile(label: "API", value: net?.api_ms.map { "\(Int($0))" } ?? "—",
                             unit: "ms", size: 20)
                }
                LatencyChart(model: model, height: chart, compact: true)
            }
        } accessory: {
            Button("Details", action: open).buttonStyle(.link).font(.system(size: 11))
        }
    }
}

struct PlanGlancePanel: View {
    @ObservedObject var model: TowerModel
    let open: () -> Void
    var body: some View {
        let plan = model.state?.plan
        Panel("Plan usage", symbol: "gauge.with.dots.needle.33percent") {
            if model.usageGate != nil {
                UsageGateNote(model: model, roomy: false)
            } else if plan?.disabled == true {
                Text("Live limits are off — no Claude runs, no permission prompts.")
                    .font(.system(size: 11)).foregroundStyle(.secondary)
            } else if let p = plan, p.ok == true {
                HStack(spacing: 8) {
                    ForEach(PopPref.trackedLimits(p), id: \.label) { l in
                        RingStat(label: l.label, bucket: l.bucket, size: 62)
                    }
                }
                .shimmer(p.refreshing == true)
            } else if let e = plan?.error {
                Text("Unavailable — \(e)").font(.system(size: 11))
                    .foregroundStyle(Color(nsColor: .systemOrange))
            } else {
                HStack(spacing: 8) {
                    ProgressView().controlSize(.small)
                    Text("Reading /usage…").font(.system(size: 11)).foregroundStyle(.secondary)
                }
            }
        } accessory: {
            Button("Details", action: open).buttonStyle(.link).font(.system(size: 11))
        }
    }
}

/// A ring, its percent at the center, the label and reset beneath.
struct RingStat: View {
    let label: String
    let bucket: GPlanBucket?
    var size: CGFloat = 96
    var body: some View {
        if let pct = bucket?.pct {
            VStack(spacing: 6) {
                ZStack {
                    RingGauge(fraction: Double(pct) / 100, tint: ringTint(pct),
                              lineWidth: size * 0.11)
                    Text("\(pct)%")
                        .font(.system(size: size * 0.22, weight: .semibold, design: .rounded))
                        .monospacedDigit()
                        .contentTransition(.numericText())
                }
                .frame(width: size, height: size)
                VStack(spacing: 1) {
                    Text(label).font(.system(size: size > 80 ? 13 : 11, weight: .medium))
                    if let r = bucket?.resetDisplay {
                        Text("resets \(r)").font(.system(size: 10)).foregroundStyle(.tertiary)
                    }
                }
            }
            .frame(maxWidth: .infinity)
        }
    }
    /// White → yellow → red by the user's thresholds — color only when it means something.
    private func ringTint(_ pct: Int) -> Color {
        pct >= dangerAt() ? Color(nsColor: .systemRed)
            : pct >= warnAt() ? Color(nsColor: .systemYellow) : Color.primary
    }
}

struct GuardControlsPanel: View {
    @ObservedObject var model: TowerModel
    var body: some View {
        let g = model.state?.guardInfo
        Panel("Guard", symbol: "shield.lefthalf.filled") {
            VStack(spacing: 6) {
                PanelRow(title: "Enforce", symbol: "hand.raised",
                         detail: "Hold Claude while you're outside \(model.targetName)") {
                    Toggle("", isOn: Binding(get: { g?.enforce ?? true },
                                             set: { model.setEnforce($0) }))
                        .labelsHidden().toggleStyle(.tower).controlSize(.small)
                }
                Divider()
                PanelRow(title: "Scope", symbol: "line.3.horizontal.decrease") {
                    Picker("", selection: Binding(get: { g?.block_all ?? false }, set: {
                        model.send(["cmd": "scope", "block_all": $0])
                    })) {
                        Text("Claude only").tag(false)
                        Text("All traffic").tag(true)
                    }
                    .labelsHidden().pickerStyle(.menu).fixedSize()
                }
                Divider()
                PanelRow(title: "Country", symbol: "globe") {
                    CountryPicker(model: model).fixedSize()
                }
            }
        }
    }
}

/// The fence's country: a quiet capsule that opens a searchable list.
struct CountryPicker: View {
    @ObservedObject var model: TowerModel
    @State private var open = false
    @State private var hovering = false

    var body: some View {
        Button { open.toggle() } label: {
            HStack(spacing: 7) {
                Text(flag(model.targetCC)).font(.system(size: 14))
                Text(model.targetName)
                    .font(.system(size: 13, weight: .medium))
                    .lineLimit(1)
                Image(systemName: "chevron.up.chevron.down")
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundStyle(.secondary)
            }
            .foregroundStyle(.primary)      // a Form dims button labels
            .padding(.leading, 9).padding(.trailing, 10).frame(height: 26)
            .background(Capsule(style: .continuous)
                .fill(Color.primary.opacity(open ? 0.14 : hovering ? 0.10 : 0.06)))
            .contentShape(Capsule(style: .continuous))
        }
        .buttonStyle(.plain)
        .onHover { h in withAnimation(.easeOut(duration: 0.12)) { hovering = h } }
        .popover(isPresented: $open, arrowEdge: .bottom) {
            CountrySearch(model: model) { cc in
                if cc != model.targetCC { model.send(["cmd": "country", "cc": cc]) }
                open = false
            }
        }
        .help("The country Claude is fenced to")
        .accessibilityLabel("Country")
        .accessibilityValue(model.targetName)
    }
}

/// Type to filter, ↑↓ to move, ⏎ to pick, esc to close. With no query it
/// leads with what matters — the current fence, and where you are now.
struct CountrySearch: View {
    @ObservedObject var model: TowerModel
    let pick: (String) -> Void
    @State private var query = ""
    @State private var cursor = 0
    @State private var keys: Any?
    @FocusState private var searching: Bool

    private struct Row: Identifiable {
        let id: Int
        let cc: String
        let name: String
        let note: String?
        let header: String?
    }

    private var here: String? {
        guard let l = model.state?.location, l.status == "OK" else { return nil }
        return l.country_cc
    }

    private var rows: [Row] {
        let q = query.trimmingCharacters(in: .whitespaces).lowercased()
        let all = COUNTRIES.sorted { $0.name < $1.name }
        var out: [Row] = []
        func add(_ c: (cc: String, name: String), note: String? = nil, header: String? = nil) {
            out.append(Row(id: out.count, cc: c.cc, name: c.name, note: note, header: header))
        }
        if q.isEmpty {
            if let cur = all.first(where: { $0.cc == model.targetCC }) {
                add(cur, note: here == cur.cc ? "Fenced · you're here" : "Fenced", header: "Suggested")
            }
            if let h = here, h != model.targetCC, let c = all.first(where: { $0.cc == h }) {
                add(c, note: "You're here", header: out.isEmpty ? "Suggested" : nil)
            }
            for (i, c) in all.enumerated() { add(c, header: i == 0 ? "All countries" : nil) }
            return out
        }
        func rank(_ c: (cc: String, name: String)) -> Int? {
            let n = c.name.lowercased()
            if c.cc.lowercased() == q { return 0 }
            if n.hasPrefix(q) { return 1 }
            if n.split(separator: " ").contains(where: { $0.hasPrefix(q) }) { return 2 }
            if n.contains(q) { return 3 }
            return nil
        }
        let hits = all.compactMap { c in rank(c).map { (c, $0) } }
            .sorted { $0.1 != $1.1 ? $0.1 < $1.1 : $0.0.name < $1.0.name }
        for (c, _) in hits { add(c) }
        return out
    }

    var body: some View {
        let list = rows
        VStack(spacing: 0) {
            HStack(spacing: 7) {
                Image(systemName: "magnifyingglass")
                    .font(.system(size: 12, weight: .medium)).foregroundStyle(.secondary)
                TextField("Search countries", text: $query)
                    .textFieldStyle(.plain).font(.system(size: 13))
                    .focused($searching)
                    .onSubmit { if list.indices.contains(cursor) { pick(list[cursor].cc) } }
                if !query.isEmpty {
                    Button { query = "" } label: {
                        Image(systemName: "xmark.circle.fill").foregroundStyle(.tertiary)
                    }
                    .buttonStyle(.plain)
                    .help("Clear")
                }
            }
            .padding(.horizontal, 10).frame(height: 32)
            .background(RoundedRectangle(cornerRadius: 8, style: .continuous)
                .fill(Color.primary.opacity(0.06)))
            .padding(10)
            Divider()
            if list.isEmpty {
                VStack(spacing: 6) {
                    Image(systemName: "globe").font(.system(size: 20)).foregroundStyle(.tertiary)
                    Text("No country matches “\(query)”")
                        .font(.system(size: 12)).foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(alignment: .leading, spacing: 0) {
                            ForEach(list) { r in
                                if let h = r.header {
                                    Text(h)
                                        .font(.system(size: 11, weight: .semibold))
                                        .foregroundStyle(.tertiary)
                                        .padding(.horizontal, 10)
                                        .padding(.top, r.id == 0 ? 4 : 10).padding(.bottom, 3)
                                }
                                row(r, on: r.id == cursor).id(r.id)
                            }
                        }
                        .padding(.horizontal, 6).padding(.vertical, 6)
                    }
                    .onChange(of: cursor) { _, c in proxy.scrollTo(c) }
                }
            }
        }
        .frame(width: 290, height: 380)
        .onChange(of: query) { cursor = 0 }
        .onAppear {
            searching = true
            keys = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { e in
                switch e.keyCode {
                case 125: cursor = min(cursor + 1, max(rows.count - 1, 0)); return nil
                case 126: cursor = max(cursor - 1, 0); return nil
                default: return e
                }
            }
        }
        .onDisappear { if let k = keys { NSEvent.removeMonitor(k) }; keys = nil }
    }

    private func row(_ r: Row, on: Bool) -> some View {
        Button { pick(r.cc) } label: {
            HStack(spacing: 9) {
                Text(flag(r.cc)).font(.system(size: 15))
                Text(r.name).font(.system(size: 13)).lineLimit(1)
                if let n = r.note {
                    Text(n).font(.system(size: 11)).foregroundStyle(.tertiary).lineLimit(1)
                }
                Spacer(minLength: 6)
                if r.cc == model.targetCC {
                    Image(systemName: "checkmark")
                        .font(.system(size: 11, weight: .bold))
                } else {
                    Text(r.cc).font(TowerDesign.Font.mono(10)).foregroundStyle(.tertiary)
                }
            }
            .padding(.horizontal, 8).frame(height: 30)
            .background(RoundedRectangle(cornerRadius: 7, style: .continuous)
                .fill(Color.primary.opacity(on ? 0.10 : 0)))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { if $0 { cursor = r.id } }
        .accessibilityAddTraits(r.cc == model.targetCC ? .isSelected : [])
    }
}

// --------------------------------------------------------------------------- //
// Agents — Mail-style master–detail: grouped session list, full inspector.
// --------------------------------------------------------------------------- //
struct AgentsPage: View {
    @ObservedObject var model: TowerModel
    @ObservedObject var selected: SelectedTab
    @Environment(\.dashLayout) private var layout

    var body: some View {
        let sessions = model.sessionsOrdered
        if model.state?.agents == nil || sessions.isEmpty {
            DashPage { banners; EmptyFloor() }
        } else {
            let current = sessions.first { $0.id == selected.session } ?? sessions[0]
            let list = SessionList(model: model, sessions: sessions, picked: current.id) {
                selected.session = $0
            }
            // Side by side only when the inspector keeps real room (≥ ~560 pt);
            // narrower, the list rides on top and the inspector gets the width.
            if layout.width >= 860 {
                let listW: CGFloat = layout.width >= 1180 ? 320 : 270
                HStack(spacing: 0) {
                    list.frame(width: listW)
                    Divider()
                    inspector(current, width: layout.width - listW - 1)
                }
            } else {
                VStack(spacing: 0) {
                    list.frame(height: min(CGFloat(sessions.count) * 54 + 44, 200))
                    Divider()
                    inspector(current, width: layout.width)
                }
            }
        }
    }

    /// The inspector lays itself out by its *own* width, not the window's.
    private func inspector(_ s: GAgentSession, width: CGFloat) -> some View {
        let inner = min(width, 980) - 48
        return ScrollView {
            VStack(alignment: .leading, spacing: DashStyle.gap) {
                banners
                AgentInspector(model: model, session: s)
            }
            .environment(\.dashLayout, DashLayout(width: inner, height: layout.height))
            .padding(.horizontal, 24).padding(.top, 18).padding(.bottom, 28)
            .frame(maxWidth: 980, alignment: .topLeading)
            .frame(maxWidth: .infinity, alignment: .topLeading)
        }
    }

    @ViewBuilder private var banners: some View {
        if !model.collisions.isEmpty || model.unguardedCount > 0 || model.pinnedCount > 0 {
            VStack(spacing: 0) {
                ForEach(model.collisions) { c in CollisionBanner(collision: c) }
                if model.unguardedCount > 0 {
                    GuardGapBanner(model: model, count: model.unguardedCount, unguarded: true)
                } else if model.pinnedCount > 0 {
                    GuardGapBanner(model: model, count: model.pinnedCount, unguarded: false)
                }
            }
            .padding(.horizontal, -10)
        }
    }
}

struct SessionList: View {
    @ObservedObject var model: TowerModel
    let sessions: [GAgentSession]
    let picked: String
    let pick: (String) -> Void
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        let needs = model.needsYou
        let working = model.workingAgents
        let seen = Set((needs + working).map(\.id))
        let rest = sessions.filter { !seen.contains($0.id) }
        ScrollView {
            // A plain VStack: lazy stacks skip insert/remove transitions.
            VStack(alignment: .leading, spacing: 1) {
                group("Needs you", needs, tint: needs.isEmpty ? nil : Color(nsColor: .systemOrange))
                group("Working", working)
                group("Resting", rest)
            }
            .padding(.horizontal, 8).padding(.vertical, 10)
            .animation(.tower(TowerDesign.Motion.reorder, reduced: reduceMotion),
                       value: needs.map { $0.id + ($0.status ?? "") } + ["|"]
                            + working.map(\.id) + ["|"] + rest.map(\.id))
        }
        .background(Color.primary.opacity(0.015))
    }

    @ViewBuilder private func group(_ title: String, _ list: [GAgentSession], tint: Color? = nil) -> some View {
        if !list.isEmpty {
            HStack {
                Text(title.uppercased())
                    .font(.system(size: 10, weight: .semibold)).tracking(0.6)
                    .foregroundStyle(tint.map { AnyShapeStyle($0) } ?? AnyShapeStyle(.tertiary))
                Spacer()
                Text("\(list.count)").font(TowerDesign.Font.counter).foregroundStyle(.tertiary)
            }
            .padding(.horizontal, 10).padding(.top, 10).padding(.bottom, 4)
            ForEach(list) { s in
                SessionRow(model: model, session: s, selected: s.id == picked) { pick(s.id) }
                    .towerRow()
            }
        }
    }
}

/// Everything about one session, for a window with room to say it: who and
/// where, what it's doing, what it was asked and answered, its subagents in
/// full, its numbers, its health, its timeline, and the actions.
struct AgentInspector: View {
    @ObservedObject var model: TowerModel
    let session: GAgentSession
    @Environment(\.dashLayout) private var layout

    var body: some View {
        let st = AgentStatus(raw: session.status)
        let tier = ModelTier(family: session.model_family)
        let subs = session.subagentsOrdered
        let running = subs.filter(\.working).count
        let roomy = layout.width >= 620
        VStack(alignment: .leading, spacing: DashStyle.gap) {
            if roomy {
                HStack(alignment: .center, spacing: 12) {
                    header(st, tier)
                    Spacer(minLength: 12)
                    actions(st)
                }
            } else {
                header(st, tier)
                actions(st)
            }

            if let now = nowLine {
                HStack(alignment: .firstTextBaseline, spacing: 10) {
                    Image(systemName: st == .working ? "waveform" : st.symbol)
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(st == .working ? AnyShapeStyle(.secondary) : AnyShapeStyle(st.color))
                    Text(now).font(.system(size: 13)).textSelection(.enabled)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(14)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(DashStyle.surface())
            }

            LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 12),
                                     count: layout.width >= 500 ? 4 : 2), spacing: 12) {
                numberTile("Tools", session.ticks?.tools_done, "wrench.and.screwdriver")
                numberTile("Files", session.ticks?.files, "doc")
                numberTile("Subagents", session.ticks?.subagents, "point.3.connected.trianglepath.dotted")
                numberTile("Errors", session.ticks?.errors, "xmark.octagon",
                           warn: (session.ticks?.errors ?? 0) > 0)
            }

            if !subs.isEmpty {
                Panel("Subagents", symbol: "point.3.connected.trianglepath.dotted") {
                    SubagentTree(subagents: subs, rail: 8,
                                 limit: 40, detailed: true)
                } accessory: {
                    Text("\(running) running · \(subs.count - running) back")
                }
            }

            if layout.width >= 760 {
                HStack(alignment: .top, spacing: DashStyle.gap) {
                    VStack(spacing: DashStyle.gap) { asked; health; facts }
                        .frame(maxWidth: .infinity)
                    timeline.frame(maxWidth: .infinity)
                }
            } else {
                asked; health; facts; timeline
            }
        }
    }

    private func header(_ st: AgentStatus, _ tier: ModelTier) -> some View {
        HStack(alignment: .center, spacing: 16) {
            ModelGlyphView(tier: tier, working: st == .working, size: 44)
            VStack(alignment: .leading, spacing: 4) {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text(session.project_name ?? "agent")
                        .font(.system(size: 20, weight: .bold)).lineLimit(1)
                        .layoutPriority(1)
                    ModelMeta(session: session)
                    UnguardedChip(model: model, session: session)
                }
                HStack(spacing: 5) {
                    Image(systemName: st.symbol).font(.system(size: 11, weight: .semibold))
                    Text(st.phrase).font(.system(size: 12, weight: .medium))
                    if let since = session.status_since {
                        Text("· for \(agoString(sinceEpoch: since))")
                            .font(.system(size: 12)).foregroundStyle(.tertiary)
                    }
                    if let b = session.git_branch {
                        Text("·").foregroundStyle(.quaternary)
                        Image(systemName: "arrow.triangle.branch").font(.system(size: 10))
                            .foregroundStyle(.tertiary)
                        Text(b).font(TowerDesign.Font.mono(11)).foregroundStyle(.secondary)
                            .lineLimit(1).truncationMode(.middle)
                    }
                }
                .lineLimit(1)
                .foregroundStyle(st.color)
            }
        }
    }

    private func actions(_ st: AgentStatus) -> some View {
        HStack(spacing: 8) {
            if st.needsYouRank != nil {
                Button("Dismiss") { model.send(["cmd": "dismiss", "session_id": session.id]) }
                    .help("Clear this from Needs You")
            }
            if session.focusable == true {
                Button {
                    model.send(["cmd": "focus", "session_id": session.id])
                } label: { Label("Show Terminal", systemImage: "terminal") }
                    .buttonStyle(InkButtonStyle())
            }
        }
        .controlSize(.regular)
    }

    private var nowLine: String? {
        switch AgentStatus(raw: session.status) {
        case .pendingTool:
            if let p = session.pending_tool {
                return "Waiting for approval · \(p.name ?? "tool") \(p.detail ?? "")"
            }
            return session.activity
        case .done, .waitingInput: return session.result ?? session.activity
        default: return session.activity ?? session.title
        }
    }

    private func numberTile(_ label: String, _ v: Int?, _ symbol: String, warn: Bool = false) -> some View {
        StatTile(label: label, value: v.map(String.init) ?? "—", symbol: symbol,
                 tint: warn ? Color(nsColor: .systemRed) : .primary, size: 22)
            .padding(.horizontal, 14).padding(.vertical, 12)
            .background(DashStyle.surface())
    }

    @ViewBuilder private var asked: some View {
        if let prompt = session.last_prompt, !prompt.isEmpty {
            Panel("Asked", symbol: "text.bubble") {
                Text(prompt).font(.system(size: 12)).foregroundStyle(.secondary)
                    .textSelection(.enabled).lineLimit(8)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    @ViewBuilder private var health: some View {
        if session.health?.level == "warn", let rs = session.health?.reasons, !rs.isEmpty {
            Panel("Health", symbol: "stethoscope") {
                VStack(alignment: .leading, spacing: 6) {
                    ForEach(rs, id: \.self) { r in
                        Label(r, systemImage: "exclamationmark.triangle.fill")
                            .font(.system(size: 12))
                            .foregroundStyle(Color(nsColor: .systemYellow))
                    }
                }
            }
        }
    }

    private var facts: some View {
        Panel("Details", symbol: "info.circle") {
            Grid(alignment: .leading, horizontalSpacing: 16, verticalSpacing: 7) {
                fact("Folder", session.cwd)
                fact("Branch", session.git_branch)
                fact("Terminal", session.tty)
                fact("Process", session.pid.map { "pid \($0)" + (session.kind == "background" ? " · background" : "") })
                fact("Started", session.started.map { agoString(sinceEpoch: $0) + " ago" })
                fact("Guard", session.guarded == true ? "through Tower"
                     : session.guarded == false ? "direct — started before the guard" : nil)
                fact("Session", session.session_id)
            }
        }
    }

    private var timeline: some View {
        Panel("Timeline", symbol: "clock") {
            TimelineRows(model: model, sessionID: session.session_id, limit: 14)
        }
    }

    @ViewBuilder private func fact(_ k: String, _ v: String?) -> some View {
        if let v, !v.isEmpty {
            GridRow {
                Text(k).font(.system(size: 12)).foregroundStyle(.tertiary)
                    .gridColumnAlignment(.trailing)
                Text(v)
                    .font(k == "Session" || k == "Folder" ? TowerDesign.Font.mono(11) : .system(size: 12))
                    .foregroundStyle(.secondary).textSelection(.enabled)
                    .lineLimit(1).truncationMode(.middle)
            }
        }
    }
}

// --------------------------------------------------------------------------- //
// Network — the weather station.
// --------------------------------------------------------------------------- //
struct NetworkPage: View {
    @ObservedObject var model: TowerModel
    @Environment(\.dashLayout) private var layout
    var body: some View {
        NetVerdictHero(model: model)
        if layout.isWide {
            HStack(alignment: .top, spacing: DashStyle.gap) {
                VStack(spacing: DashStyle.gap) {
                    latency(height: layout.isVast ? 340 : 250)
                    SpeedTestPanel(model: model)
                }
                .frame(maxWidth: .infinity)
                TrafficPanel(model: model, limit: layout.isVast ? 40 : 26)
                    .frame(width: layout.isVast ? 460 : 360)
            }
        } else {
            latency(height: 200)
            SpeedTestPanel(model: model)
            TrafficPanel(model: model, limit: 14)
        }
    }

    private func latency(height: CGFloat) -> some View {
        Panel("Latency", symbol: "waveform.path.ecg") {
            LatencyChart(model: model, height: height)
        } accessory: {
            HStack(spacing: 12) {
                legend("Anthropic API", TowerDesign.ink)
                legend("Internet", .gray)
                Text("last \(max((model.state?.net?.history?.count ?? 0) / 6, 1)) min")
                    .foregroundStyle(.tertiary)
            }
        }
    }
    private func legend(_ t: String, _ c: Color) -> some View {
        HStack(spacing: 5) {
            Capsule().fill(c).frame(width: 10, height: 3)
            Text(t)
        }
    }
}

struct NetVerdictHero: View {
    @ObservedObject var model: TowerModel
    @Environment(\.dashLayout) private var layout
    var body: some View {
        if layout.isWide {
            HStack(spacing: 16) { verdict; Spacer(minLength: 16); readings }
                .padding(20).background(DashStyle.surface())
        } else {
            VStack(alignment: .leading, spacing: 16) { verdict; readings }
                .padding(20)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(DashStyle.surface())
        }
    }

    private var verdict: some View {
        let v = model.netVerdict
        let net = model.state?.net
        return HStack(spacing: 16) {
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .fill(v.tint.opacity(0.14))
                .frame(width: 52, height: 52)
                .overlay(Image(systemName: v.symbol)
                    .font(.system(size: 22, weight: .semibold))
                    .foregroundStyle(v.tint))
            VStack(alignment: .leading, spacing: 3) {
                Text(v.title).font(.system(size: 20, weight: .bold))
                Text(v.detail).font(.system(size: 13)).foregroundStyle(.secondary)
                if let c = net?.checked {
                    Text("Checked \(agoString(sinceEpoch: c)) ago")
                        .font(.system(size: 11)).foregroundStyle(.tertiary)
                }
            }
        }
    }

    private var readings: some View {
        let net = model.state?.net
        return HStack(spacing: 28) {
                StatTile(label: "Internet", value: net?.internet_ms.map { "\(Int($0))" } ?? "—",
                         unit: "ms", symbol: "network", size: 28)
                    .fixedSize()
                StatTile(label: "Anthropic API", value: net?.api_ms.map { "\(Int($0))" } ?? "—",
                         unit: "ms", symbol: "server.rack", size: 28)
                    .fixedSize()
        }
    }
}

/// Dual-series latency: the API line over a soft area, the internet line
/// quieter beneath; hover anywhere for that moment's numbers. The compact
/// form is a bare sparkline.
struct LatencyChart: View {
    @ObservedObject var model: TowerModel
    var height: CGFloat = 220
    var compact = false
    @State private var hover: Date?

    private struct Point: Identifiable {
        let id: Int; let date: Date; let internet: Double?; let api: Double?
    }

    var body: some View {
        let pts = points
        if pts.count > 1 {
            chart(pts).frame(height: height)
        } else {
            HStack(spacing: 8) {
                ProgressView().controlSize(.small)
                Text("Collecting samples…").font(.system(size: 11)).foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, minHeight: height)
        }
    }

    private var points: [Point] {
        (model.state?.net?.history ?? []).enumerated().compactMap { i, s in
            s.t.map { Point(id: i, date: Date(timeIntervalSince1970: $0),
                            internet: s.internet_ms, api: s.api_ms) }
        }
    }

    private func chart(_ pts: [Point]) -> some View {
        let pick = compact ? nil : hover.flatMap { h in
            pts.min { abs($0.date.timeIntervalSince(h)) < abs($1.date.timeIntervalSince(h)) }
        }
        let area = LinearGradient(colors: [TowerDesign.ink.opacity(compact ? 0.14 : 0.26),
                                           TowerDesign.ink.opacity(0.0)],
                                  startPoint: .top, endPoint: .bottom)
        return Chart {
            ForEach(pts) { p in
                if let v = p.api {
                    AreaMark(x: .value("t", p.date), y: .value("ms", v))
                        .foregroundStyle(area)
                        .interpolationMethod(.monotone)
                    LineMark(x: .value("t", p.date), y: .value("ms", v),
                             series: .value("kind", "Anthropic API"))
                        .foregroundStyle(by: .value("kind", "Anthropic API"))
                        .interpolationMethod(.monotone)
                        .lineStyle(StrokeStyle(lineWidth: compact ? 1.3 : 1.8,
                                               lineCap: .round, lineJoin: .round))
                }
                if let v = p.internet, !compact {
                    LineMark(x: .value("t", p.date), y: .value("ms", v),
                             series: .value("kind", "Internet"))
                        .foregroundStyle(by: .value("kind", "Internet"))
                        .interpolationMethod(.monotone)
                        .lineStyle(StrokeStyle(lineWidth: 1.2, lineCap: .round, lineJoin: .round))
                }
            }
            if let pick {
                RuleMark(x: .value("t", pick.date))
                    .foregroundStyle(Color.primary.opacity(0.18))
                    .lineStyle(StrokeStyle(lineWidth: 1))
                    .annotation(position: .top, spacing: 4,
                                overflowResolution: .init(x: .fit(to: .chart), y: .disabled)) {
                        hoverCard(pick)
                    }
                if let v = pick.api {
                    PointMark(x: .value("t", pick.date), y: .value("ms", v))
                        .foregroundStyle(TowerDesign.ink).symbolSize(36)
                }
            }
        }
        .chartForegroundStyleScale(["Anthropic API": TowerDesign.ink, "Internet": Color.gray])
        .chartLegend(.hidden)
        .chartXAxis(compact ? .hidden : .automatic)
        .chartYAxis(compact ? .hidden : .automatic)
        .chartYAxis {
            AxisMarks(position: .leading, values: .automatic(desiredCount: 4)) { v in
                AxisGridLine().foregroundStyle(Color.primary.opacity(0.06))
                AxisValueLabel {
                    if let d = v.as(Double.self) { Text("\(Int(d)) ms").font(.system(size: 10)) }
                }
            }
        }
        .chartXAxis {
            AxisMarks(values: .automatic(desiredCount: 5)) { _ in
                AxisValueLabel(format: .dateTime.hour().minute()).font(.system(size: 10))
            }
        }
        .chartXSelection(value: $hover)
    }

    private func hoverCard(_ p: Point) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(p.date, format: .dateTime.hour().minute().second())
                .font(.system(size: 10)).foregroundStyle(.secondary)
            Text("API \(fmtMs(p.api))").font(.system(size: 11, weight: .semibold)).monospacedDigit()
            Text("Internet \(fmtMs(p.internet))").font(.system(size: 11)).monospacedDigit()
                .foregroundStyle(.secondary)
        }
        .padding(.horizontal, 8).padding(.vertical, 6)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 8, style: .continuous)
            .strokeBorder(DashStyle.rule, lineWidth: 0.5))
    }
}

struct SpeedTestPanel: View {
    @ObservedObject var model: TowerModel
    var body: some View {
        let s = model.state?.net?.speedtest
        let running = s?.running == true
        Panel("Speed test", symbol: "speedometer") {
            HStack(spacing: 16) {
                ZStack {
                    RingGauge(fraction: running ? (s?.progress ?? 0) : (s?.mbps_down == nil ? 0 : 1),
                              tint: TowerDesign.ink, lineWidth: 6, marksZero: false)
                    Image(systemName: "arrow.down")
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundStyle(.secondary)
                }
                .frame(width: 52, height: 52)
                VStack(alignment: .leading, spacing: 2) {
                    if running {
                        Text("\(Int((s?.progress ?? 0) * 100))%")
                            .font(.system(size: 26, weight: .semibold, design: .rounded)).monospacedDigit()
                            .contentTransition(.numericText())
                        Text("Measuring download speed…").font(.system(size: 11)).foregroundStyle(.secondary)
                    } else if let mbps = s?.mbps_down {
                        HStack(alignment: .firstTextBaseline, spacing: 3) {
                            Text(String(format: "%.0f", mbps))
                                .font(.system(size: 26, weight: .semibold, design: .rounded)).monospacedDigit()
                            Text("Mbps").font(.system(size: 12, weight: .medium)).foregroundStyle(.secondary)
                        }
                        if let at = s?.at {
                            Text("Download · \(agoString(sinceEpoch: at)) ago")
                                .font(.system(size: 11)).foregroundStyle(.tertiary)
                        }
                    } else if let err = s?.error {
                        Text("Test failed").font(.system(size: 14, weight: .semibold))
                        Text(err).font(.system(size: 11)).foregroundStyle(Color(nsColor: .systemOrange))
                    } else {
                        Text("Not run yet").font(.system(size: 14, weight: .semibold))
                        Text("Measures your download speed on demand.")
                            .font(.system(size: 11)).foregroundStyle(.secondary)
                    }
                }
                Spacer(minLength: 12)
                Button(running ? "Testing…" : "Run Test") { model.send(["cmd": "speedtest"]) }
                    .buttonStyle(InkButtonStyle())
                    .disabled(running)
            }
        }
    }
}

struct TrafficPanel: View {
    @ObservedObject var model: TowerModel
    var limit: Int
    var body: some View {
        let recent = Array((model.state?.recent ?? []).suffix(limit).reversed())
        let g = model.state?.guardInfo
        Panel("Live traffic", symbol: "arrow.left.arrow.right", flush: true) {
            if recent.isEmpty {
                Text("No traffic seen yet — route Claude through the guard first")
                    .font(.system(size: 11)).foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .center).padding(16)
            } else {
                VStack(spacing: 0) {
                    ForEach(Array(recent.enumerated()), id: \.offset) { i, e in
                        HStack(spacing: 10) {
                            Circle()
                                .fill(e.action == "blocked" ? Color(nsColor: .systemOrange)
                                      : Color.primary.opacity(0.35))
                                .frame(width: 6, height: 6)
                            Text(e.t ?? "").font(TowerDesign.Font.mono(10.5))
                                .foregroundStyle(.tertiary)
                            Text(e.host ?? "?").font(.system(size: 12))
                                .lineLimit(1).truncationMode(.middle)
                            Spacer(minLength: 6)
                            if e.kind == "claude" { Chip(text: "Claude", tint: TowerDesign.ink) }
                            if e.action == "blocked" {
                                Chip(text: "held", tint: Color(nsColor: .systemOrange))
                            }
                        }
                        .padding(.horizontal, 16).frame(height: 26)
                        .background(i % 2 == 1 ? Color.primary.opacity(0.025) : Color.clear)
                    }
                }
            }
        } accessory: {
            Text("\(g?.allowed ?? 0) allowed · \(g?.blocked ?? 0) blocked").monospacedDigit()
        }
    }
}

// --------------------------------------------------------------------------- //
// Usage — plan rings, the local estimate, the model mix, the week.
// --------------------------------------------------------------------------- //
struct UsagePage: View {
    @ObservedObject var model: TowerModel
    @Environment(\.dashLayout) private var layout
    // Two even rows: what your plan says (limits) beside what it cost (the
    // local estimate), then the week beside where it went. Paired panels
    // share one height, so nothing hangs short of its neighbour.
    var body: some View {
        if layout.isWide {
            pair { PlanLimitsPanel(model: model) } _: { EstimatePanel(model: model) }
            pair { WeekPanel(model: model, height: 150) } _: { ContributionsPanel(model: model) }
        } else {
            PlanLimitsPanel(model: model)
            EstimatePanel(model: model)
            WeekPanel(model: model, height: 140)
            ContributionsPanel(model: model)
        }
    }

    private func pair<A: View, B: View>(@ViewBuilder _ a: () -> A, @ViewBuilder _ b: () -> B) -> some View {
        HStack(alignment: .top, spacing: DashStyle.gap) {
            a().frame(maxWidth: .infinity)
            b().frame(maxWidth: .infinity)
        }
        .environment(\.panelFill, true)
        .fixedSize(horizontal: false, vertical: true)
    }
}

/// The limits you track as slim rows — name, reset, percent, one bar each.
/// White until your warn line, then yellow, then red.
struct PlanLimitsPanel: View {
    @ObservedObject var model: TowerModel
    var body: some View {
        let plan = model.state?.plan
        Panel("Plan limits", symbol: "gauge.with.dots.needle.33percent") {
            if model.usageGate != nil {
                UsageGateNote(model: model)
            } else if plan?.disabled == true {
                Text("Live limits are off — turn them on in Settings.")
                    .font(.system(size: 12)).foregroundStyle(.secondary)
            } else if let p = plan, p.ok == true {
                VStack(alignment: .leading, spacing: 14) {
                    ForEach(PopPref.trackedLimits(p), id: \.label) { l in
                        if let b = l.bucket, let pct = b.pct { limitRow(l.label, pct, b) }
                    }
                    if let l24 = p.last24h {
                        Text("\(l24.requests ?? 0) requests · \(l24.sessions ?? 0) sessions in the last 24 hours")
                            .font(.system(size: 11)).foregroundStyle(.tertiary).monospacedDigit()
                    }
                }
                .shimmer(p.refreshing == true)
            } else if let e = plan?.error {
                Text("Unavailable — \(e)").font(.system(size: 12))
                    .foregroundStyle(Color(nsColor: .systemOrange))
            } else {
                HStack(spacing: 8) {
                    ProgressView().controlSize(.small)
                    Text("Reading /usage…").font(.system(size: 12)).foregroundStyle(.secondary)
                }
            }
        } accessory: {
            if plan?.refreshing == true { Text("Updating…") }
            else if let u = plan?.updated, plan?.ok == true { Text("\(agoString(sinceEpoch: u)) ago") }
        }
    }

    private func limitRow(_ label: String, _ pct: Int, _ b: GPlanBucket) -> some View {
        let tint = pct >= dangerAt() ? Color(nsColor: .systemRed)
            : pct >= warnAt() ? Color(nsColor: .systemYellow) : TowerDesign.ink
        return VStack(spacing: 6) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(label).font(.system(size: 13, weight: .medium))
                Spacer(minLength: 8)
                Text(b.resetShort.map { "↻ \($0)" } ?? "")
                    .font(.system(size: 11)).monospacedDigit().foregroundStyle(.tertiary)
                    .help(b.resets_at.map { "Resets \(resetClock($0))" } ?? "")
                Text("\(pct)%")
                    .font(.system(size: 15, weight: .semibold, design: .rounded)).monospacedDigit()
                    .foregroundStyle(pct >= warnAt() ? AnyShapeStyle(tint) : AnyShapeStyle(.primary))
                    .contentTransition(.numericText())
                    .frame(minWidth: 42, alignment: .trailing)
            }
            ShareBar(fraction: Double(pct) / 100, tint: tint)
        }
    }
}

/// What it cost at list price — today first, the session and week beside it,
/// the pace, and the mix by model as quiet rows. Monochrome: no model colors.
struct EstimatePanel: View {
    @ObservedObject var model: TowerModel
    var body: some View {
        let u = model.state?.usage
        let bm = u?.byModel ?? []
        Panel("Cost estimate", symbol: "dollarsign.circle") {
            VStack(alignment: .leading, spacing: 14) {
                HStack(alignment: .firstTextBaseline, spacing: 18) {
                    StatTile(label: "Today", value: fmtCost(u?.today?.cost ?? 0),
                             detail: u?.today?.tokens.map { fmtTokens($0) + " tokens" }, size: 24)
                    StatTile(label: "Session", value: fmtCost(u?.session?.cost ?? 0), size: 16)
                    StatTile(label: "This week", value: fmtCost(u?.week?.cost ?? 0),
                             detail: u?.pace?.projected_week_cost.map { "on pace for ~\(fmtCost($0))" }
                                ?? weekSincePhrase(u?.week), size: 16)
                        .help(weekSincePhrase(u?.week).map { "This week runs \($0) — your plan's weekly window" } ?? "")
                }
                if !bm.isEmpty {
                    VStack(spacing: 8) {
                        ForEach(bm) { m in
                            HStack(spacing: 10) {
                                Text(modelDisplay(m.model)).font(.system(size: 12, weight: .medium))
                                    .frame(width: 84, alignment: .leading)
                                ShareBar(fraction: m.pct / 100, tint: TowerDesign.ink.opacity(0.75))
                                Text("\(Int(m.pct.rounded()))%").font(TowerDesign.Font.counter)
                                    .foregroundStyle(.tertiary).frame(width: 34, alignment: .trailing)
                                Text(fmtCost(m.cost)).font(.system(size: 12, weight: .semibold))
                                    .monospacedDigit().frame(minWidth: 52, alignment: .trailing)
                            }
                        }
                    }
                }
            }
        } accessory: {
            Text("list price · not your plan").foregroundStyle(.tertiary)
        }
    }
}

/// The week in dollars — one bar a day, today in full ink; hover a day for it.
struct WeekPanel: View {
    @ObservedObject var model: TowerModel
    var height: CGFloat
    /// Grow the chart into whatever height its column has left.
    var fill = false
    @State private var pick: String?
    private static let parse: DateFormatter = {
        let f = DateFormatter(); f.dateFormat = "yyyy-MM-dd"; return f
    }()
    private static let label: DateFormatter = {
        let f = DateFormatter(); f.setLocalizedDateFormatFromTemplate("EEE"); return f
    }()

    var body: some View {
        let series = model.state?.usage?.series ?? []
        let total = series.reduce(0) { $0 + $1.cost }
        let today = series.last?.day
        Panel("Last 7 days", symbol: "chart.bar.xaxis") {
            if !series.contains(where: { $0.cost > 0 }) {
                Text("No local usage recorded yet").font(.system(size: 11)).foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, minHeight: height * 0.6)
            } else {
                Chart(series) { d in
                    let name = day(d.day)
                    BarMark(x: .value("day", name), y: .value("cost", d.cost), width: .ratio(0.5))
                        .foregroundStyle(TowerDesign.ink.opacity(d.day == today ? 1 : 0.45))
                        .cornerRadius(4)
                        .opacity(pick == nil || pick == name ? 1 : 0.4)
                        .annotation(position: .top, spacing: 4) {
                            if pick == name {
                                Text(fmtCost(d.cost))
                                    .font(.system(size: 10, weight: .semibold)).monospacedDigit()
                                    .padding(.horizontal, 6).padding(.vertical, 3)
                                    .background(.regularMaterial, in: Capsule())
                            }
                        }
                }
                .chartXSelection(value: $pick)
                .chartYAxis {
                    AxisMarks(position: .leading, values: .automatic(desiredCount: 3)) { v in
                        AxisGridLine().foregroundStyle(Color.primary.opacity(0.06))
                        AxisValueLabel {
                            if let n = v.as(Double.self) { Text(fmtCost(n)).font(.system(size: 10)) }
                        }
                    }
                }
                .chartXAxis {
                    AxisMarks { _ in AxisValueLabel().font(.system(size: 10)) }
                }
                .frame(minHeight: height, maxHeight: fill ? .infinity : height)
            }
        } accessory: {
            if total > 0 { Text("\(fmtCost(total)) in 7 days").monospacedDigit() }
        }
    }

    private func day(_ s: String) -> String {
        Self.parse.date(from: s).map { Self.label.string(from: $0) } ?? String(s.suffix(5))
    }
}

/// Claude's own read on where your limits go (/usage's "what's contributing"):
/// its top suggestions by the share of usage they'd touch, and the subagent,
/// skill and MCP server that cost the most — per 24 h or 7 d. Approximate,
/// this Mac only; shares overlap.
struct ContributionsPanel: View {
    @ObservedObject var model: TowerModel
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var window = "24h"

    var body: some View {
        let windows = model.state?.plan?.windows ?? [:]
        let w = windows[window] ?? windows.values.first
        Panel("Where your limits go", symbol: "chart.pie") {
            if model.usageGate != nil || windows.isEmpty {
                Text(model.usageGate != nil ? "Paused with your plan limits." : "Nothing reported yet.")
                    .font(.system(size: 12)).foregroundStyle(.tertiary)
            } else {
                VStack(alignment: .leading, spacing: 12) {
                    ForEach((w?.tips ?? []).prefix(3)) { t in
                        VStack(alignment: .leading, spacing: 5) {
                            HStack(alignment: .firstTextBaseline, spacing: 8) {
                                Text(t.text ?? "").font(.system(size: 12, weight: .medium)).lineLimit(1)
                                Spacer(minLength: 6)
                                Text("\(t.pct ?? 0)%").font(TowerDesign.Font.counter).foregroundStyle(.secondary)
                            }
                            ShareBar(fraction: Double(t.pct ?? 0) / 100, tint: TowerDesign.ink.opacity(0.75))
                        }
                        .help(t.hint ?? "")
                    }
                    let tops = topLine(w)
                    if !tops.isEmpty {
                        Text(tops).font(.system(size: 11)).foregroundStyle(.tertiary).lineLimit(2)
                    }
                }
                .animation(.tower(TowerDesign.Motion.settle, reduced: reduceMotion), value: window)
            }
        } accessory: {
            if windows.count > 1 {
                Picker("", selection: $window) {
                    Text("24h").tag("24h")
                    Text("7d").tag("7d")
                }
                .pickerStyle(.segmented).labelsHidden().fixedSize().controlSize(.small)
            }
        }
    }

    /// "Top: general-purpose 21% · /claude-in-chrome 3% · safari 1%"
    private func topLine(_ w: GUsageWindow?) -> String {
        let firsts = ["subagents", "skills", "mcp_servers"].compactMap { w?.top?[$0]?.first }
            .map { "\($0.name ?? "?") \($0.pct ?? 0)%" }
        return firsts.isEmpty ? "" : "Top: " + firsts.joined(separator: " · ")
    }
}

/// A thin share bar — a capsule track and its fill, settling on the spring.
struct ShareBar: View {
    let fraction: Double
    var tint: Color = TowerDesign.ink
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    var body: some View {
        Capsule().fill(Color.primary.opacity(0.08))
            .overlay(alignment: .leading) {
                GeometryReader { g in
                    Capsule().fill(tint)
                        .frame(width: max(3, g.size.width * min(max(fraction, 0), 1)))
                }
            }
            .frame(height: 5)
            .animation(.tower(TowerDesign.Motion.settle, reduced: reduceMotion), value: fraction)
    }
}

// --------------------------------------------------------------------------- //
// Settings — one short native form: the guard, the menu bar, the popover (its
// sections, dragged into order), the limits you track, and about.
// --------------------------------------------------------------------------- //
struct SettingsPage: View {
    @ObservedObject var model: TowerModel
    @AppStorage("menubarMode") var mode = "session"
    @AppStorage("warnAt") var warn = 60
    @AppStorage("dangerAt") var danger = 85
    @AppStorage(PopPref.needsBadge) var needsBadge = true
    @AppStorage(PopPref.planStyle) var planStyle = "rings"
    @AppStorage(PopPref.density) var density = "comfy"
    @AppStorage(PopPref.resting) var showResting = true
    @AppStorage(PopPref.subagents) var subagents = true
    @AppStorage(PopPref.ip) var showIP = true
    @AppStorage(PopPref.limitSession) var trackSession = true
    @AppStorage(PopPref.limitWeek) var trackWeek = true
    @AppStorage(PopPref.limitFable) var trackFable = true

    var body: some View {
        let g = model.state?.guardInfo
        Form {
            Section("Guard") {
                LabeledContent("Country") { CountryPicker(model: model).fixedSize() }
                Toggle(isOn: Binding(get: { g?.enforce ?? true }, set: { model.setEnforce($0) })) {
                    Text("Enforce")
                    Text("Hold Claude while you're outside \(model.targetName)")
                }
                Picker("Scope", selection: Binding(get: { g?.block_all ?? false }, set: {
                    model.send(["cmd": "scope", "block_all": $0])
                })) {
                    Text("Claude only").tag(false)
                    Text("All traffic").tag(true)
                }
            }

            Section {
                Picker("Shows", selection: $mode) {
                    Text("Icon only").tag("off")
                    Text("Session %").tag("session")
                    Text("Week %").tag("week")
                    Text("Closest limit").tag("auto")
                }
                Toggle(isOn: $needsBadge) {
                    Text("Needs-you badge")
                    Text("Counts failures, approvals and questions — never a finished turn")
                }
                LabeledContent("Highlight") {
                    HStack(spacing: 8) {
                        thresholdMenu($warn, range: stride(from: 40, through: 90, by: 5), dot: .systemYellow)
                        thresholdMenu($danger, range: stride(from: 60, through: 100, by: 5), dot: .systemRed)
                    }
                }
            } header: { Text("Menu bar") }
            .onChange(of: [mode]) { refreshIcon() }
            .onChange(of: [warn, danger]) { refreshIcon() }
            .onChange(of: needsBadge) { refreshIcon() }

            Section {
                SectionOrderList()
                Picker("Plan usage", selection: $planStyle) {
                    Text("Rings").tag("rings")
                    Text("Bars").tag("bars")
                }
                .pickerStyle(.segmented)
                Picker("Density", selection: $density) {
                    Text("Comfortable").tag("comfy")
                    Text("Compact").tag("compact")
                }
                .pickerStyle(.segmented)
                Toggle("Subagent trees", isOn: $subagents)
                Toggle("Resting agents", isOn: $showResting)
                Toggle("Public IP address", isOn: $showIP)
            } header: {
                Text("Popover")
            } footer: {
                Text("Drag to reorder. The guard stays on top, the buttons at the bottom.")
                    .font(.system(size: 11)).foregroundStyle(.secondary)
            }

            Section {
                Toggle("Session", isOn: $trackSession)
                Toggle("Weekly", isOn: $trackWeek)
                Toggle("Fable", isOn: $trackFable)
                Toggle(isOn: Binding(
                    get: { model.state?.settings?.plan_enabled ?? true },
                    set: { model.send(["cmd": "planfetch", "on": $0]) })) {
                    Text("Read live limits")
                    Text("A sandboxed `claude -p /usage` — off keeps only the local estimate")
                }
            } header: { Text("Plan limits") }
            .onChange(of: [trackSession, trackWeek, trackFable]) { refreshIcon() }

            Section {
                LabeledContent("Version", value: model.state?.version ?? "—")
                LabeledContent("Reset") {
                    Button("Reset to Defaults…", role: .destructive) { confirmReset() }
                }
            }
        }
        .formStyle(.grouped)
    }

    private func refreshIcon() { (NSApp.delegate as? AppDelegate)?.updateIcon() }

    /// "● 60%": the threshold's color, then a plain pop-up of values — the
    /// native control, so the whole thing is one obvious click target.
    private func thresholdMenu(_ v: Binding<Int>, range: StrideThrough<Int>, dot: NSColor) -> some View {
        HStack(spacing: 6) {
            Circle().fill(Color(nsColor: dot)).frame(width: 7, height: 7)
            Picker("", selection: v) {
                ForEach(Array(range), id: \.self) { Text("\($0)%").tag($0) }
            }
            .labelsHidden().pickerStyle(.menu).fixedSize()
        }
    }

    private func confirmReset() {
        let a = NSAlert()
        a.messageText = "Reset Tower to defaults?"
        a.informativeText = "Removes routing from settings.json and disables keep-awake."
        a.addButton(withTitle: "Reset")
        a.addButton(withTitle: "Cancel")
        if a.runModal() == .alertFirstButtonReturn { model.send(["cmd": "reset"]) }
    }
}

// --------------------------------------------------------------------------- //
// The popover's sections, in order, as rows you pick up and drag. The row you
// hold lifts (scale + shadow) and follows the pointer 1:1; the others glide
// out of its way on a spring the moment it crosses their midline, with a soft
// trackpad tick per slot; let go and it settles into the gap. Arrow-key and
// VoiceOver moves ride the same spring.
// --------------------------------------------------------------------------- //
struct SectionOrderList: View {
    @AppStorage(PopPref.order) private var order = PopPref.defaultOrder
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var dragging: PopSection?
    @State private var dragY: CGFloat = 0          // pointer travel since pickup
    @State private var target = 0                  // the slot it would land in
    @State private var settle: CGFloat = 0         // leftover travel, sprung to 0 on drop
    private let rowH: CGFloat = 40

    var body: some View {
        let list = PopSection.order(order)
        let from = dragging.flatMap { list.firstIndex(of: $0) } ?? 0
        VStack(spacing: 0) {
            ForEach(Array(list.enumerated()), id: \.element) { i, sec in
                let held = dragging == sec
                SectionOrderRow(section: sec, held: held, divider: i < list.count - 1 && !held)
                    .frame(height: rowH)
                    .offset(y: held ? dragY : (settle != 0 && sec == list[safe: target] ? settle : shift(i, from: from)))
                    .zIndex(held ? 1 : 0)
                    .animation(held ? nil : spring, value: target)
                    .gesture(drag(sec, index: i, count: list.count))
                    .accessibilityAction(named: "Move Up") { step(sec, -1) }
                    .accessibilityAction(named: "Move Down") { step(sec, 1) }
                    .contextMenu {
                        Button("Move Up") { step(sec, -1) }.disabled(i == 0)
                        Button("Move Down") { step(sec, 1) }.disabled(i == list.count - 1)
                    }
            }
        }
        .coordinateSpace(name: "order")
        .padding(.vertical, -4)
    }

    private var spring: Animation {
        .tower(.spring(response: 0.32, dampingFraction: 0.82), reduced: reduceMotion)
    }

    /// Rows between the pickup slot and the target slide one row toward the gap.
    private func shift(_ i: Int, from: Int) -> CGFloat {
        guard dragging != nil else { return 0 }
        if from < target, i > from, i <= target { return -rowH }
        if target < from, i >= target, i < from { return rowH }
        return 0
    }

    private func drag(_ sec: PopSection, index: Int, count: Int) -> some Gesture {
        DragGesture(minimumDistance: 3, coordinateSpace: .named("order"))
            .onChanged { v in
                if dragging == nil {
                    withAnimation(spring) { dragging = sec }
                    target = index
                }
                // Stay inside the list: never drag past the first or last slot.
                let lo = -CGFloat(index) * rowH, hi = CGFloat(count - 1 - index) * rowH
                dragY = min(max(v.translation.height, lo), hi)
                let t = min(max(index + Int((dragY / rowH).rounded()), 0), count - 1)
                if t != target {
                    target = t
                    NSHapticFeedbackManager.defaultPerformer.perform(.alignment, performanceTime: .now)
                }
            }
            .onEnded { _ in
                var l = PopSection.order(order)
                guard let from = l.firstIndex(of: sec) else { dragging = nil; return }
                let residual = dragY - CGFloat(target - from) * rowH
                // Commit the order and drop every shift in one still frame —
                // the neighbours are already where the new order puts them —
                // then spring the held row's leftover travel into its slot.
                var t = Transaction(); t.disablesAnimations = true
                withTransaction(t) {
                    l.move(fromOffsets: IndexSet(integer: from), toOffset: target > from ? target + 1 : target)
                    order = l.map(\.rawValue).joined(separator: ",")
                    dragging = nil; dragY = 0
                    settle = residual
                }
                DispatchQueue.main.async { withAnimation(spring) { settle = 0 } }
            }
    }

    private func step(_ sec: PopSection, _ d: Int) {
        var l = PopSection.order(order)
        guard let i = l.firstIndex(of: sec), l.indices.contains(i + d) else { return }
        withAnimation(spring) {
            l.swapAt(i, i + d)
            order = l.map(\.rawValue).joined(separator: ",")
        }
    }
}

private extension Array {
    subscript(safe i: Int) -> Element? { indices.contains(i) ? self[i] : nil }
}

struct SectionOrderRow: View {
    let section: PopSection
    let held: Bool
    let divider: Bool
    @AppStorage private var on: Bool
    @State private var hovering = false

    init(section: PopSection, held: Bool, divider: Bool) {
        self.section = section; self.held = held; self.divider = divider
        _on = AppStorage(wrappedValue: true, section.visibilityKey)
    }

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: "line.3.horizontal")
                .font(.system(size: 11, weight: .medium))
                .foregroundStyle(held || hovering ? .secondary : .quaternary)
                .frame(width: 14)
            Image(systemName: section.symbol)
                .font(.system(size: 12))
                .foregroundStyle(on ? .secondary : .quaternary)
                .frame(width: 18)
            Text(section.title)
                .foregroundStyle(on ? AnyShapeStyle(.primary) : AnyShapeStyle(.tertiary))
            Spacer(minLength: 8)
            Toggle("", isOn: $on.animation(.easeOut(duration: 0.15)))
                .labelsHidden().toggleStyle(.tower).controlSize(.mini)
        }
        .padding(.horizontal, held ? 8 : 0)
        .frame(maxHeight: .infinity)
        .background {
            if held {
                RoundedRectangle(cornerRadius: 9, style: .continuous)
                    .fill(Color(nsColor: .controlBackgroundColor))
                    .overlay(RoundedRectangle(cornerRadius: 9, style: .continuous)
                        .strokeBorder(Color.primary.opacity(0.12), lineWidth: 0.5))
                    .shadow(color: .black.opacity(0.28), radius: 12, y: 6)
                    .padding(.horizontal, -8)
            }
        }
        .overlay(alignment: .bottom) {
            if divider { Rectangle().fill(DashStyle.rule).frame(height: 0.5).padding(.leading, 24) }
        }
        .scaleEffect(held ? 1.025 : 1)
        .contentShape(Rectangle())
        .onHover { h in
            hovering = h
            if h { NSCursor.openHand.set() } else { NSCursor.arrow.set() }
        }
        .accessibilityElement(children: .combine)
        .accessibilityHint("Drag to reorder")
    }
}
