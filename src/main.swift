// Tower — entry point. Top-level code must live in main.swift when the app
// is compiled from multiple Swift files (see build.sh).

import AppKit

// Top-level code runs on the main thread at launch; assert that so the
// main-actor-isolated AppDelegate (it drives all UI) can be constructed here.
MainActor.assumeIsolated {
    let app = NSApplication.shared
    let delegate = AppDelegate()
    app.delegate = delegate
    app.run()
}
