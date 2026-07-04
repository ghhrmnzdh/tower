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

struct KeepAwakeMenu: View {
    @ObservedObject var model: TowerModel
    var body: some View {
        let mode = model.state?.keepawake?.mode ?? "off"
        let label = ["idle": "Lid open", "clamshell": "Lid closed"][mode] ?? "Off"
        Menu(label) {
            Button("Off — allow sleep") { model.send(["cmd": "keepawake", "on": false, "mode": "off"]) }
            Button("Awake while lid open") { model.send(["cmd": "keepawake", "on": true, "mode": "idle"]) }
            Button("Awake even with lid closed") {
                (NSApp.delegate as? AppDelegate)?.explainThenEnableClamshell(model: model)
            }
        }
        .menuStyle(.borderlessButton).fixedSize()
        .font(.system(size: 11, weight: .semibold, design: .rounded))
    }
}
