// Tower — notifications. The daemon publishes agent state transitions in
// agents.events; the app turns the ones that matter into macOS notifications:
//   → failed / → pending_tool / → asking: always when fresh; a STALE one (a
//     sleep / App-Nap backlog) only if the agent is still in that state, since
//     it's still actionable.
//   → done: only when fresh AND the popover hasn't been opened in the last 60s —
//     never interrupt someone who's already watching, and never toast a turn
//     that finished long ago (the dashboard's "while you were away" owns the
//     past). "Fresh" = the transition is younger than maxEventAge.
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
    /// Transitions older than this are history, not news. Normal detect→deliver
    /// latency is ~2-4s (2-cycle debounce + ~1s state write + ~1s poll), so this
    /// can never swallow a fresh toast; it exists solely to drop the minutes-old
    /// backlog an App-Nap / system-sleep stall leaves behind.
    private static let maxEventAge: TimeInterval = 180

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
        // Advance the watermark over the whole fresh batch BEFORE deciding what
        // to post: a transition we choose to drop (stale, or popover-suppressed)
        // is dropped for good, never re-delivered on a later poll.
        lastSeenEvent = fresh.compactMap(\.t).max() ?? lastSeenEvent

        let now = Date().timeIntervalSince1970
        for e in fresh {
            let to = AgentStatus(raw: e.to)
            let age = now - (e.t ?? 0)
            switch to {
            case .failed, .pendingTool, .asking:
                // News while fresh; a stale one (a sleep/App-Nap backlog) is only
                // worth a banner if the agent is STILL in that state — i.e. still
                // blocked on you right now.
                if age <= Self.maxEventAge || currentStatus(of: e.session_id) == to {
                    post(for: e, status: to)
                }
            case .done, .waitingInput:
                // A finished turn is only news while it's fresh, and never while
                // you're already watching. Older completions live in the
                // dashboard's "while you were away" list, not as a late banner.
                if age <= Self.maxEventAge,
                   Date().timeIntervalSince(lastPopoverOpen) > 60 {
                    post(for: e, status: to)
                }
            default:
                break
            }
        }
    }

    /// The session's current status from the latest snapshot, or nil if it has
    /// dropped off the list. Lets a stale failed/asking/pending transition still
    /// notify when it's genuinely still awaiting the user.
    private func currentStatus(of sid: String?) -> AgentStatus? {
        guard let sid, !sid.isEmpty,
              let s = model?.agentSessions.first(where: { $0.session_id == sid })
        else { return nil }
        return AgentStatus(raw: s.status)
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
                content.body = session?.result ?? session?.title ?? "The result is ready."
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
