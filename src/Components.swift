// Tower — shared SwiftUI components: shimmer, danger alerts, subagent trees.

import SwiftUI

// Modern shimmer that sweeps across the masked content while active.
struct Shimmer: ViewModifier {
    var active: Bool
    @State private var phase: CGFloat = -1
    @Environment(\.surfaceVisible) private var visible
    func body(content: Content) -> some View {
        content.overlay {
            // Off screen the sweep is dropped (not just hidden) so its
            // repeatForever animation stops; it restarts on the next appearance.
            if active && visible {
                GeometryReader { g in
                    LinearGradient(colors: [.clear, Color.white.opacity(0.85), .clear],
                                   startPoint: .leading, endPoint: .trailing)
                        .frame(width: g.size.width * 0.6)
                        .offset(x: phase * g.size.width * 1.5)
                        .blendMode(.plusLighter)
                }
                .allowsHitTesting(false)
                .mask(content)
                .onAppear {
                    phase = -0.8
                    withAnimation(.linear(duration: 1.1).repeatForever(autoreverses: false)) {
                        phase = 1.1
                    }
                }
            }
        }
    }
}
extension View { func shimmer(_ active: Bool) -> some View { modifier(Shimmer(active: active)) } }

// Two-stage confirmation for anything that lets Claude reach the API WITHOUT
// the guard (route off, enforce off, quit). Wording escalates when agents are
// working right now. Attach once to a view root; the model drives both stages.
struct DangerAlerts: ViewModifier {
    @ObservedObject var model: TowerModel
    func body(content: Content) -> some View {
        content
            .alert(model.danger1?.title ?? "",
                   isPresented: Binding(get: { model.danger1 != nil },
                                        set: { if !$0 { model.cancelDanger() } }),
                   presenting: model.danger1) { _ in
                Button("Cancel", role: .cancel) { model.cancelDanger() }
                Button(model.danger1?.confirmLabel ?? "Turn off", role: .destructive) {
                    model.confirmDangerStage1()
                }
            } message: { d in
                Text(dangerBody(d.message))
            }
            .alert("Are you absolutely sure?",
                   isPresented: Binding(get: { model.danger2 != nil },
                                        set: { if !$0 { model.cancelDanger() } }),
                   presenting: model.danger2) { _ in
                Button("Keep the guard on", role: .cancel) { model.cancelDanger() }
                Button("Yes, disable protection", role: .destructive) {
                    model.confirmDangerStage2()
                }
            } message: { _ in
                Text("This lets Claude Code reach the API with NO location "
                     + "guard — requests can go out from the wrong country. "
                     + dangerAgentClause())
            }
    }
    private func dangerBody(_ base: String) -> String {
        model.agentsWorking > 0
            ? base + "\n\n⚠︎ " + dangerAgentClause()
            : base
    }
    private func dangerAgentClause() -> String {
        let n = model.agentsWorking
        return n > 0
            ? "\(n) Claude agent\(n == 1 ? " is" : "s are") working right now "
              + "and will immediately send unguarded requests."
            : "No agents are working right now."
    }
}
extension View {
    func dangerAlerts(_ model: TowerModel) -> some View {
        modifier(DangerAlerts(model: model))
    }
}

// --------------------------------------------------------------------------- //
// Subagents — a parent's fan-out, drawn as a tree hanging off its model mark.
// A hairline rail drops from the parent's glyph; each child branches off it
// with a status node (a solid neutral dot while running, a
// quiet check once done). Running children read in full, finished ones step
// back to tertiary. No motion of its own: the rail grows/shrinks with the
// list (state change), it never pulses.
// --------------------------------------------------------------------------- //
struct SubagentTree: View {
    let subagents: [GSubagent]
    /// x of the rail, in the tree's own coordinates (the parent glyph's center).
    var rail: CGFloat = TowerDesign.Size.rowGlyph / 2
    /// Rows shown before the rest fold into "+N more".
    var limit: Int = 4
    /// Wide surfaces add each child's live activity and tool count.
    var detailed: Bool = false

    var body: some View {
        let shown = Array(subagents.prefix(limit))
        let rest = subagents.count - shown.count
        VStack(alignment: .leading, spacing: 0) {
            ForEach(Array(shown.enumerated()), id: \.element.id) { i, sub in
                SubagentNode(sub: sub, rail: rail,
                             last: i == shown.count - 1 && rest == 0,
                             detailed: detailed)
            }
            if rest > 0 {
                let running = subagents.dropFirst(limit).filter(\.working).count
                HStack(spacing: 0) {
                    TreeRail(last: true).frame(width: rail + 10)
                    Text("+\(rest) more" + (running > 0 ? " · \(running) running" : ""))
                        .font(TowerDesign.Font.caption.weight(.medium))
                        .foregroundStyle(.tertiary)
                }
                .frame(height: 16)
                .towerRow()
            }
        }
    }
}

struct SubagentNode: View {
    let sub: GSubagent
    let rail: CGFloat
    let last: Bool
    let detailed: Bool

    var body: some View {
        HStack(spacing: 0) {
            TreeRail(last: last)
                .frame(width: rail + 10)
                .overlay(alignment: .trailing) { node.offset(x: 3.5) }
            HStack(spacing: 6) {
                Text(sub.typeName)
                    .font(TowerDesign.Font.mono(9.5))
                    .foregroundStyle(sub.working ? AnyShapeStyle(.primary) : AnyShapeStyle(.tertiary))
                    .padding(.horizontal, 5).frame(height: 15)
                    .background(RoundedRectangle(cornerRadius: 4, style: .continuous)
                        .fill(Color.primary.opacity(sub.working ? 0.09 : 0.05)))
                Text(sub.desc ?? sub.now)
                    .font(TowerDesign.Font.activity)
                    .foregroundStyle(sub.working ? AnyShapeStyle(.secondary) : AnyShapeStyle(.tertiary))
                    .lineLimit(1).truncationMode(.tail)
                if detailed, sub.desc != nil {
                    Text(sub.now)
                        .font(TowerDesign.Font.activity).foregroundStyle(.tertiary)
                        .lineLimit(1).truncationMode(.tail)
                        .layoutPriority(-1)
                }
                Spacer(minLength: 6)
                if detailed, let n = sub.tools, n > 0 {
                    Text("\(n) ✓").font(TowerDesign.Font.counter).foregroundStyle(.tertiary)
                }
                Text(sub.elapsed)
                    .font(TowerDesign.Font.counter)
                    .foregroundStyle(sub.working ? AnyShapeStyle(.secondary) : AnyShapeStyle(.quaternary))
            }
            .padding(.leading, 8)
        }
        .frame(height: 19)
        .help(sub.desc.map { "\($0)\n\(sub.now)" } ?? sub.now)
        .towerRow()
    }

    @ViewBuilder private var node: some View {
        if sub.working {
            Circle().fill(Color.primary.opacity(0.7)).frame(width: 6, height: 6)
        } else {
            Image(systemName: "checkmark")
                .font(.system(size: 7, weight: .heavy))
                .foregroundStyle(.tertiary)
                .frame(width: 7, height: 7)
        }
    }
}

/// One segment of the rail: down through the row (or to its middle, for the
/// last child) with a rounded elbow out to the node.
struct TreeRail: View {
    let last: Bool
    var body: some View {
        Canvas { ctx, size in
            let x = size.width - 10, mid = size.height / 2, r: CGFloat = 4
            var p = Path()
            p.move(to: CGPoint(x: x, y: 0))
            p.addLine(to: CGPoint(x: x, y: mid - r))
            p.addQuadCurve(to: CGPoint(x: x + r, y: mid), control: CGPoint(x: x, y: mid))
            p.addLine(to: CGPoint(x: size.width - 1, y: mid))
            if !last {
                p.move(to: CGPoint(x: x, y: mid - r))
                p.addLine(to: CGPoint(x: x, y: size.height))
            }
            ctx.stroke(p, with: .color(.primary.opacity(0.16)), lineWidth: 1)
        }
    }
}
