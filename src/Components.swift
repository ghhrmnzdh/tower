// Tower — shared SwiftUI components: cards, meters, shimmer, small controls.

import SwiftUI

let SPRING = Animation.spring(response: 0.42, dampingFraction: 0.86)

struct Card<Content: View>: View {
    @ViewBuilder var content: Content
    var body: some View {
        content
            .padding(13)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.primary.opacity(0.045),
                        in: RoundedRectangle(cornerRadius: 13, style: .continuous))
    }
}

// Modern shimmer that sweeps across the masked content while active.
struct Shimmer: ViewModifier {
    var active: Bool
    @State private var phase: CGFloat = -1
    func body(content: Content) -> some View {
        content.overlay {
            if active {
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

struct Meter: View {
    let fraction: Double
    let color: Color
    var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .leading) {
                Capsule().fill(Color.secondary.opacity(0.16))
                Capsule().fill(
                    LinearGradient(colors: [color.opacity(0.85), color],
                                   startPoint: .leading, endPoint: .trailing))
                    .frame(width: max(3, geo.size.width * fraction))
            }
        }
        .frame(height: 7)
        .animation(SPRING, value: fraction)
    }
}

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

// Keep awake — the dashboard card. The beacon (the tower's lamp) states it at a
// glance; the segmented control sets it; a line names the consequence. Picking
// "Lid closed" routes through the pre-explained admin prompt, never a surprise.
struct KeepAwakeCard: View {
    @ObservedObject var model: TowerModel
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    var body: some View {
        let mode = model.keepAwakeMode
        GroupBox("Keep awake") {
            VStack(alignment: .leading, spacing: 12) {
                HStack(spacing: 12) {
                    BeaconView(mode: model.awakeGlow, size: 34)
                        .frame(width: 34, height: 34)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(KeepAwakeCopy.title(mode))
                            .font(.system(size: 15, weight: .semibold))
                        Text(KeepAwakeCopy.line(mode))
                            .font(.system(size: 12)).foregroundStyle(.secondary)
                    }
                    Spacer(minLength: 6)
                }
                Picker("", selection: modeBinding) {
                    Text("Off").tag("off")
                    Text("Lid open").tag("idle")
                    Text("Lid closed").tag("clamshell")
                }
                .pickerStyle(.segmented).labelsHidden()
                HStack(spacing: 7) {
                    Image(systemName: "info.circle")
                        .font(.system(size: 10)).foregroundStyle(.tertiary)
                    Text(note(mode)).font(.system(size: 11)).foregroundStyle(.tertiary)
                }
            }
            .padding(6)
            .animation(.tower(TowerDesign.Motion.settle, reduced: reduceMotion), value: mode)
        }
    }

    /// The picker reflects real daemon state; choosing "Lid closed" hands off to
    /// the pre-explained admin flow instead of writing state optimistically, so
    /// the segment only moves once keep-awake actually engages.
    private var modeBinding: Binding<String> {
        Binding(get: { model.keepAwakeMode }, set: { newMode in
            if newMode == "clamshell" {
                (NSApp.delegate as? AppDelegate)?.explainThenEnableClamshell(model: model)
            } else {
                model.send(["cmd": "keepawake", "on": newMode != "off", "mode": newMode])
            }
        })
    }

    private func note(_ mode: String) -> String {
        switch mode {
        case "idle":      return "No permission needed — caffeinate keeps the system awake."
        case "clamshell": return "macOS asks for your password once, only to run pmset disablesleep."
        default:          return "Turn on to keep long agents running when you step away."
        }
    }
}
