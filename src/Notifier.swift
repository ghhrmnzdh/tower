// Tower — notifications. The daemon publishes agent state transitions in
// agents.events; the app turns the ones that matter into macOS notifications:
//   → failed / → pending_tool / → asking: always (that's the product).
//   → done: only if the popover hasn't been opened in the last 60s — never
//     interrupt someone who's already watching.
// Clicking a notification focuses that agent's terminal. If authorization is
// denied, the menubar badge carries the signal alone — no nagging.

import AppKit
import UserNotifications

final class Notifier: NSObject, UNUserNotificationCenterDelegate {
    private weak var model: TowerModel?
    private var lastSeenEvent: Double = Date().timeIntervalSince1970
    private var authState: UNAuthorizationStatus = .notDetermined
    private var requested = false
    /// Set by AppDelegate whenever the popover opens.
    var lastPopoverOpen: Date = .distantPast

    init(model: TowerModel) {
        self.model = model
        super.init()
        let center = UNUserNotificationCenter.current()
        center.delegate = self
        center.getNotificationSettings { [weak self] s in
            self?.authState = s.authorizationStatus
        }
    }

    /// Call once per state poll.
    func process() {
        guard let model = model,
              let events = model.state?.agents?.events, !events.isEmpty else { return }
        let fresh = events.filter { ($0.t ?? 0) > lastSeenEvent }
        guard !fresh.isEmpty else { return }
        lastSeenEvent = fresh.compactMap(\.t).max() ?? lastSeenEvent

        for e in fresh {
            let to = AgentStatus(raw: e.to)
            switch to {
            case .failed, .pendingTool, .asking:
                post(for: e, status: to)
            case .done, .waitingInput:
                if Date().timeIntervalSince(lastPopoverOpen) > 60 {
                    post(for: e, status: to)
                }
            default:
                break
            }
        }
    }

    private func post(for event: GAgentEvent, status: AgentStatus) {
        requestIfNeeded { [weak self] granted in
            guard granted, let self = self, let model = self.model else { return }
            let session = model.agentSessions.first { $0.session_id == event.session_id }
            let project = session?.project_name ?? "an agent"
            let content = UNMutableNotificationContent()
            switch status {
            case .failed:
                content.title = "\(project) hit an error"
                content.body = session?.title ?? "The agent failed — it needs a look."
            case .pendingTool:
                content.title = "\(project) is waiting for approval"
                content.body = session?.pending_tool?.name.map { "Tool: \($0)" }
                    ?? "A tool call needs your OK."
            case .asking:
                content.title = "\(project) asked you a question"
                content.body = session?.title ?? "It's blocked on your answer."
            default:
                content.title = "\(project) finished its turn"
                content.body = session?.title ?? "The result is ready."
            }
            content.userInfo = ["session_id": event.session_id ?? ""]
            let req = UNNotificationRequest(
                identifier: "tower-\(event.session_id ?? UUID().uuidString)-\(status.rawValue)",
                content: content, trigger: nil)
            UNUserNotificationCenter.current().add(req)
        }
    }

    /// Lazy authorization: first notification-worthy moment asks, not launch.
    private func requestIfNeeded(_ then: @escaping (Bool) -> Void) {
        switch authState {
        case .authorized, .provisional:
            then(true)
        case .denied:
            then(false)   // badge-only mode, no nag
        default:
            guard !requested else { return then(false) }
            requested = true
            UNUserNotificationCenter.current()
                .requestAuthorization(options: [.alert, .sound]) { [weak self] granted, _ in
                    self?.authState = granted ? .authorized : .denied
                    then(granted)
                }
        }
    }

    // Click → focus that agent.
    func userNotificationCenter(_ center: UNUserNotificationCenter,
                                didReceive response: UNNotificationResponse,
                                withCompletionHandler completion: @escaping () -> Void) {
        if let sid = response.notification.request.content.userInfo["session_id"] as? String,
           !sid.isEmpty {
            DispatchQueue.main.async { [weak self] in
                self?.model?.send(["cmd": "focus", "session_id": sid])
            }
        }
        completion()
    }

    // Show banners even while the app is "active" (we're a menubar agent).
    func userNotificationCenter(_ center: UNUserNotificationCenter,
                                willPresent notification: UNNotification,
                                withCompletionHandler completion:
                                    @escaping (UNNotificationPresentationOptions) -> Void) {
        completion([.banner, .sound])
    }
}
