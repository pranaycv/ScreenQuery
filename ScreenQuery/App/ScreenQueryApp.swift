import AppKit
import SwiftUI

@main
struct ScreenQueryApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate

    var body: some Scene {
        MenuBarExtra {
            MenuBarContent(
                model: appDelegate.model,
                permissions: appDelegate.model.permissions
            )
        } label: {
            Image(systemName: "viewfinder")
                .accessibilityLabel("ScreenQuery")
        }
        .menuBarExtraStyle(.menu)
    }
}

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
    let model = AppModel()

    func applicationDidFinishLaunching(_ notification: Notification) {
        installQuitMenu()
        model.start()
    }

    func applicationWillTerminate(_ notification: Notification) {
        model.stop()
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        false
    }

    /// Gives the accessory app a Quit item so Command-Q works while Settings is key.
    private func installQuitMenu() {
        let appMenu = NSMenu()
        appMenu.addItem(
            NSMenuItem(
                title: "Quit ScreenQuery",
                action: #selector(NSApplication.terminate(_:)),
                keyEquivalent: "q"
            )
        )
        let item = NSMenuItem()
        item.submenu = appMenu
        let main = NSMenu()
        main.addItem(item)
        NSApp.mainMenu = main
    }
}

struct MenuBarContent: View {
    @ObservedObject var model: AppModel
    @ObservedObject var permissions: PermissionCenter

    var body: some View {
        Text("ScreenQuery")
        Text("Hotkey  ⇧ S P")
        Divider()
        Button("Capture Screen") { model.capture() }
        Button("Settings…") { model.showSettings() }
        if needsPermissions {
            Button("Permissions Needed…") { model.showSettings() }
        }
        Divider()
        Button("Quit ScreenQuery") { NSApp.terminate(nil) }
            .keyboardShortcut("q")
    }

    private var needsPermissions: Bool {
        !permissions.screenRecording
            || !permissions.accessibility
            || !permissions.inputMonitoring
            || !permissions.hotkeyTapInstalled
    }
}
