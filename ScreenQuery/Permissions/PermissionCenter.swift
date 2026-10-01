import AppKit
import ApplicationServices
import CoreGraphics
import Darwin
import Foundation

@MainActor
final class PermissionCenter: ObservableObject {
    @Published var screenRecording = false
    @Published var accessibility = false
    @Published var inputMonitoring = false
    @Published var hotkeyTapInstalled = false

    func refresh() {
        screenRecording = CGPreflightScreenCaptureAccess()
        accessibility = AXIsProcessTrusted()
        inputMonitoring = InputMonitoringAccess.isGranted()
    }

    func requestScreenRecording() {
        _ = CGRequestScreenCaptureAccess()
        refresh()
    }

    func requestAccessibility() {
        // The prompt key is CFSTR("AXTrustedCheckOptionPrompt").
        let options = ["AXTrustedCheckOptionPrompt": true] as CFDictionary
        _ = AXIsProcessTrustedWithOptions(options)
        refresh()
    }

    func requestInputMonitoring() {
        _ = InputMonitoringAccess.request()
        refresh()
    }

    static func openScreenRecordingSettings() {
        openPrivacyPane("ScreenCapture")
    }

    static func openAccessibilitySettings() {
        openPrivacyPane("Accessibility")
    }

    static func openInputMonitoringSettings() {
        openPrivacyPane("ListenEvent")
    }

    private static func openPrivacyPane(_ anchor: String) {
        let candidates = [
            "x-apple.systempreferences:com.apple.preference.security?Privacy_\(anchor)",
            "x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension?Privacy_\(anchor)"
        ]
        for string in candidates {
            guard let url = URL(string: string) else { continue }
            if NSWorkspace.shared.open(url) {
                return
            }
        }
    }
}

enum InputMonitoringAccess {
    private static let listenEvent: UInt32 = 1
    private static let granted: UInt32 = 0

    static func isGranted() -> Bool {
        guard let check = load("IOHIDCheckAccess", as: CheckFunction.self) else { return false }
        return check(listenEvent) == granted
    }

    /// `IOHIDRequestAccess` returns `Boolean`, an unsigned char.
    static func request() -> Bool {
        guard let request = load("IOHIDRequestAccess", as: RequestFunction.self) else { return false }
        return request(listenEvent) != 0
    }

    private typealias CheckFunction = @convention(c) (UInt32) -> UInt32
    private typealias RequestFunction = @convention(c) (UInt32) -> UInt8

    private static func load<T>(_ name: String, as type: T.Type) -> T? {
        guard let handle = dlopen("/System/Library/Frameworks/IOKit.framework/Versions/A/IOKit", RTLD_LAZY) else {
            return nil
        }
        guard let symbol = dlsym(handle, name) else { return nil }
        return unsafeBitCast(symbol, to: type)
    }
}
