// Corral — entry point. Top-level code must live in main.swift when the app
// is compiled from multiple Swift files (see build.sh).

import AppKit

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
