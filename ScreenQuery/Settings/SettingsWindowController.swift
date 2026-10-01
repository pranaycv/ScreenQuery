import AppKit
import SwiftUI

@MainActor
final class SettingsWindowController {
    private var window: NSWindow?

    func show(
        settings: SettingsStore,
        permissions: PermissionCenter,
        onRecheck: @escaping () -> Void
    ) {
        if window == nil {
            let root = SettingsView(
                settings: settings,
                permissions: permissions,
                onRecheck: onRecheck
            )
            let hosting = NSHostingController(rootView: root)
            let window = NSWindow(contentViewController: hosting)
            window.title = "ScreenQuery Settings"
            window.styleMask = [.titled, .closable, .miniaturizable, .resizable]
            window.setContentSize(NSSize(width: 620, height: 720))
            window.minSize = NSSize(width: 540, height: 480)
            window.isReleasedWhenClosed = false
            window.center()
            self.window = window
        }
        NSApp.activate(ignoringOtherApps: true)
        window?.makeKeyAndOrderFront(nil)
    }
}
