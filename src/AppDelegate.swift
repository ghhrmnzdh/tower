// Tower — app delegate: status item, popover, daemon supervision, quit flow.

import AppKit
import CoreText
import SwiftUI

@MainActor
class AppDelegate: NSObject, NSApplicationDelegate {
    let model = TowerModel()
    var statusItem: NSStatusItem!
    var popover = NSPopover()
    var pollTimer: Timer?
    /// Smooth ~30fps clock, live only while the radar has motion to show.
    var animTimer: Timer?
    var daemon: Process?
    var confirmedQuit = false
    lazy var dashboard = DashboardWindowController(model: model)
    lazy var notifier = Notifier(model: model)

    func applicationDidFinishLaunching(_ note: Notification) {
        registerBundledFonts()                  // JetBrains Mono, before any UI
        UserDefaults.standard.register(defaults: PopPref.defaults)
        NSApp.setActivationPolicy(.accessory)   // menubar agent, no dock icon

        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        statusItem.button?.action = #selector(togglePopover)
        statusItem.button?.target = self
        updateIcon()

        popover.behavior = .transient
        popover.animates = true
        // Let SwiftUI's own layout size drive the popover. `.preferredContentSize`
        // makes the hosting controller publish its fitting size (and keep
        // republishing it as the content reflows), which NSPopover observes and —
        // because `animates` is true — smoothly resizes to. Without it the popover
        // is measured once from a stale/zero size: at launch the short "Starting…"
        // view is mis-sized and floats detached from the menu bar, and when the
        // daemon comes alive and the real content appears the window can't grow to
        // fit. The width is a constant (popoverWidth), so only the height animates.
        let host = NSHostingController(rootView: PopoverView(model: model))
        host.sizingOptions = [.preferredContentSize]
        popover.contentViewController = host

        launchDaemonIfNeeded()
        model.start()

        // Poll daemon state once a second: refresh the icon, fire notifications,
        // and start/stop the smooth animation clock as the radar state changes.
        pollTimer = Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { [weak self] _ in
            MainActor.assumeIsolated {
                guard let self else { return }
                self.updateIcon()
                self.notifier.process()
                self.refreshAnimClock()
            }
        }
    }

    /// The radar animates only when there's motion worth spending frames on:
    /// a hold or a verify sweep, or a calm scan while agents are actually
    /// working. Idle-clear and unguarded-off are static (and Reduce Motion
    /// freezes everything). This keeps the menu bar smooth but battery-quiet.
    private var radarShouldAnimate: Bool {
        if NSWorkspace.shared.accessibilityDisplayShouldReduceMotion { return false }
        // The lid-closed vigil breathes; idle is a still lit lamp (no clock).
        if model.awakeGlow == .clamshell { return true }
        switch model.radarState {
        case .verify, .holdNet, .holdGeo: return true
        case .clear: return model.agentsWorking > 0
        case .off: return false
        }
    }

    private func refreshAnimClock() {
        let want = radarShouldAnimate
        if want, animTimer == nil {
            let t = Timer(timeInterval: 1.0 / 30.0, repeats: true) { [weak self] _ in
                MainActor.assumeIsolated { self?.updateIcon() }
            }
            RunLoop.main.add(t, forMode: .common)   // keep ticking during menu tracking
            animTimer = t
        } else if !want, animTimer != nil {
            animTimer?.invalidate()
            animTimer = nil
        }
    }

    func openDashboard(tab: DashboardTab) {
        popover.performClose(nil)
        dashboard.open(tab: tab)
    }

    // ---- Menubar icon ---- //
    // The Tower radar (see StatusIcon.swift), refreshed at the current phase.
    // Badge text: needs-you count, then optional usage %.
    func updateIcon() {
        guard let button = statusItem.button else { return }
        let phase = Date().timeIntervalSinceReferenceDate
        let icon = menubarIcon(for: model, phase: phase)
        button.image = icon.image
        button.contentTintColor = nil   // the radar image carries its own colors
        button.image?.accessibilityDescription = icon.describe
        button.toolTip = "Tower — \(icon.describe)"

        // Freeze the button's WIDTH while the popover is open. The status item is
        // variableLength, so changing the badge text (needs-you count / usage %)
        // or toggling imagePosition RESIZES the button. The open popover is
        // anchored to this exact button (`show(relativeTo: b.bounds, of: b)`), so
        // resizing it moves the anchor out from under the popover — AppKit then
        // repositions the window and re-lays the hosted SwiftUI content, and that
        // reflow is what shoved/clipped the popover's middle every time the agent
        // count changed (e.g. dismissing an agent). The radar image is fixed-size
        // so it's safe to keep animating; only the badge is deferred, and it
        // catches up on the next poll once the popover closes.
        guard !popover.isShown else { return }

        // Badge: "⚡N" needs-you count (red when something failed), then the
        // usage % if that preference is on.
        var parts: [(String, NSColor)] = []
        let needs = model.needsYouCount
        // The ONLY number the bar may show is the needs-you attention count
        // (never a running/working count), and even that is user-toggleable.
        if needs > 0, UserDefaults.standard.bool(forKey: PopPref.needsBadge) {
            parts.append((" \(needs)", model.anyFailed ? .systemRed : .systemOrange))
        }
        let mode = UserDefaults.standard.string(forKey: "menubarMode") ?? "session"
        if let plan = model.state?.plan, plan.ok == true {
            let pct = mode == "session" ? plan.session?.pct
                    : mode == "week" ? plan.week?.pct : nil
            if let p = pct {
                parts.append((needs > 0 ? " · \(p)%" : " \(p)%", levelNSColor(p)))
            }
        }
        if parts.isEmpty {
            button.attributedTitle = NSAttributedString(string: "")
            button.title = ""
            button.imagePosition = .imageOnly
        } else {
            let s = NSMutableAttributedString()
            for (text, color) in parts {
                s.append(NSAttributedString(string: text, attributes: [
                    .foregroundColor: color,
                    .font: NSFont.monospacedDigitSystemFont(ofSize: 11, weight: .semibold),
                ]))
            }
            button.attributedTitle = s
            button.imagePosition = .imageLeading
        }
    }

    // ---- Daemon supervision ---- //
    func launchDaemonIfNeeded() {
        // The daemon is single-instance (flock), so an extra spawn is harmless —
        // it just exits. We always try; whoever wins owns the lock.
        guard let res = Bundle.main.resourcePath else { return }
        let script = res + "/towerd.py"
        guard FileManager.default.fileExists(atPath: script) else {
            alert("Missing daemon", "towerd.py was not found in the app bundle.")
            return
        }
        let py = firstExisting([
            "/opt/homebrew/bin/python3", "/usr/local/bin/python3",
            "/Library/Frameworks/Python.framework/Versions/Current/bin/python3",
            "/usr/bin/python3",
        ]) ?? "/usr/bin/python3"
        let p = Process()
        p.executableURL = URL(fileURLWithPath: py)
        p.arguments = [script]
        p.standardOutput = FileHandle.nullDevice
        p.standardError = FileHandle.nullDevice
        do { try p.run(); daemon = p } catch {
            alert("Couldn't start guard", "Failed to launch python3:\n\(error.localizedDescription)")
        }
    }

    func firstExisting(_ paths: [String]) -> String? {
        paths.first { FileManager.default.isExecutableFile(atPath: $0) }
    }

    // ---- Popover ---- //
    @objc func togglePopover() {
        if popover.isShown { popover.performClose(nil); return }
        guard let b = statusItem.button else { return }
        notifier.lastPopoverOpen = Date()
        // Standard status-item anchor: hang off the bottom edge of the button.
        // (The popover itself is height-capped in PopoverView so it can never
        // grow taller than the screen and get shoved out of place / clipped.)
        popover.show(relativeTo: b.bounds, of: b, preferredEdge: .minY)
        popover.contentViewController?.view.window?.makeKey()
    }

    // ---- Quit (Cmd-Q, or the popover button) ---- //
    @objc func confirmQuit() { NSApp.terminate(nil) }

    // Gently predict & explain a permission BEFORE macOS shows its prompt.
    func explainThenEnableClamshell(model: TowerModel) {
        popover.performClose(nil)
        let a = NSAlert()
        a.messageText = "Keep your Mac awake with the lid closed?"
        a.informativeText = """
        macOS will ask for your password once, right after this.

        Tower uses it only to run “pmset disablesleep” so long-running \
        Claude agents keep working after you close the lid. Nothing else is \
        accessed. You can switch it off anytime, and Reset removes it.
        """
        a.alertStyle = .informational
        a.addButton(withTitle: "Continue")
        a.addButton(withTitle: "Not now")
        NSApp.activate(ignoringOtherApps: true)
        if a.runModal() == .alertFirstButtonReturn {
            model.send(["cmd": "keepawake", "on": true, "mode": "clamshell"])
        }
    }

    /// Register the bundled JetBrains Mono faces (Resources/Fonts/*.ttf) with the
    /// process font manager so `Font.custom("JetBrainsMono-…")` resolves. Scoped
    /// to this process — never touches the user's installed fonts. Idempotent
    /// enough for a single launch; a duplicate-registration error is harmless.
    private func registerBundledFonts() {
        guard let dir = Bundle.main.url(forResource: "Fonts", withExtension: nil),
              let ttfs = try? FileManager.default.contentsOfDirectory(
                at: dir, includingPropertiesForKeys: nil)
        else { return }
        for url in ttfs where url.pathExtension.lowercased() == "ttf" {
            CTFontManagerRegisterFontsForURL(url as CFURL, .process, nil)
        }
    }

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        if confirmedQuit { return .terminateNow }
        popover.performClose(nil)

        // Quitting removes routing → Claude connects directly, UNGUARDED. This
        // is a dangerous action, so we double-confirm and call out any agents
        // that are working right now (they'd send unguarded requests at once).
        let working = model.agentsWorking
        let agentClause = working > 0
            ? "\n\n⚠︎ \(working) Claude agent\(working == 1 ? " is" : "s are") "
              + "working right now and will immediately send requests with no "
              + "location guard."
            : ""
        let a = NSAlert()
        a.messageText = "Quit Tower and turn off the guard?"
        a.informativeText = "Quitting removes routing from settings.json — "
            + "Claude Code goes back to a DIRECT connection with no country "
            + "guard at all." + agentClause
        a.alertStyle = .critical
        a.addButton(withTitle: "Continue…")
        a.addButton(withTitle: "Cancel")
        NSApp.activate(ignoringOtherApps: true)
        guard a.runModal() == .alertFirstButtonReturn else { return .terminateCancel }

        // Final confirmation — deliberately a second, distinct step.
        let b = NSAlert()
        b.messageText = "Are you absolutely sure?"
        b.informativeText = "This disables Claude Code's location protection "
            + "entirely until you reopen Tower." + agentClause
        b.alertStyle = .critical
        b.addButton(withTitle: "Quit & Disable Guard")
        b.addButton(withTitle: "Keep the Guard On")
        NSApp.activate(ignoringOtherApps: true)
        guard b.runModal() == .alertFirstButtonReturn else { return .terminateCancel }

        // Tell the daemon to quit → it removes routing and exits cleanly.
        confirmedQuit = true
        model.send(["cmd": "quit"])
        // Give the daemon a moment to route_off before we go.
        DispatchQueue.global().asyncAfter(deadline: .now() + 1.2) {
            DispatchQueue.main.async { NSApp.reply(toApplicationShouldTerminate: true) }
        }
        return .terminateLater
    }

    func alert(_ title: String, _ msg: String) {
        let a = NSAlert()
        a.messageText = title
        a.informativeText = msg
        a.alertStyle = .critical
        a.runModal()
    }
}
