import AppKit
import CoreGraphics
import Foundation
import os

private let captureLog = Logger(subsystem: "com.screenquery.app", category: "capture")

@MainActor
final class AppModel: ObservableObject {
    let settings = SettingsStore()
    let permissions = PermissionCenter()
    let overlay = StatusOverlayController()

    private let hotkey = GlobalHotkeyMonitor()
    private let settingsWindow = SettingsWindowController()
    private var capturing = false
    private var generation = 0

    var needsPermissions: Bool {
        !permissions.screenRecording
            || !permissions.accessibility
            || !permissions.inputMonitoring
            || !permissions.hotkeyTapInstalled
    }

    func start() {
        overlay.dismissSeconds = { [weak self] in
            max(4, self?.settings.overlayDismissSeconds ?? 12)
        }
        hotkey.onChord = { [weak self] in
            self?.capture()
        }
        recheckPermissions()
        if !permissions.screenRecording || !permissions.hotkeyTapInstalled {
            showSettings()
        }
    }

    func stop() {
        hotkey.stop()
    }

    func capture() {
        Task { await performCapture() }
    }

    func showSettings() {
        settingsWindow.show(
            settings: settings,
            permissions: permissions,
            onRecheck: { [weak self] in
                self?.recheckPermissions()
            }
        )
    }

    func recheckPermissions() {
        permissions.refresh()
        permissions.hotkeyTapInstalled = hotkey.restart()
        objectWillChange.send()
    }

    private func performCapture() async {
        if !settings.saveEnabled && !settings.llmEnabled {
            overlay.showStandalone(
                headline: "Nothing to do",
                detail: "Turn on Save, Send to LLM, or both in Settings.",
                isError: true,
                actionTitle: "Open Settings",
                action: { [weak self] in self?.showSettings() }
            )
            return
        }
        guard !capturing else { return }
        capturing = true
        generation += 1
        let token = generation
        defer { capturing = false }

        overlay.beginCapture()

        if !CGPreflightScreenCaptureAccess() {
            _ = CGRequestScreenCaptureAccess()
            permissions.refresh()
            overlay.showStandalone(
                headline: "Screen Recording required",
                detail: CaptureError.permissionDenied.localizedDescription,
                isError: true,
                actionTitle: "Open Screen Recording",
                action: { PermissionCenter.openScreenRecordingSettings() }
            )
            return
        }

        let image: CGImage
        do {
            image = try await ScreenshotService.capture()
        } catch {
            captureLog.error("Capture failed: \(error.localizedDescription, privacy: .public)")
            overlay.showStandalone(
                headline: "Capture failed",
                detail: error.localizedDescription,
                isError: true
            )
            return
        }

        if settings.saveEnabled {
            do {
                let outcome = try ScreenshotSaver.save(image, settings: settings)
                overlay.setSaved(url: outcome.url, note: outcome.note)
            } catch {
                captureLog.error("Save failed: \(error.localizedDescription, privacy: .public)")
                overlay.addError(error.localizedDescription)
            }
        }

        guard settings.llmEnabled else {
            overlay.finishPendingWork()
            return
        }

        guard let apiKey = KeychainStore.readAPIKey() else {
            overlay.addError("No API key in the Keychain. Add one in Settings to send screenshots to a model.")
            overlay.setAction(title: "Open Settings") { [weak self] in
                self?.showSettings()
            }
            overlay.finishPendingWork()
            return
        }
        let modelName = settings.llmModel.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !modelName.isEmpty else {
            overlay.addError("Set a model name in Settings.")
            overlay.finishPendingWork()
            return
        }

        overlay.setLLMPending()
        let request = LLMRequestSettings(
            baseURL: settings.llmBaseURL,
            model: modelName,
            apiKey: apiKey,
            prompt: settings.effectivePrompt
        )
        Task {
            do {
                let text = try await LLMClient().explain(image: image, settings: request)
                guard token == self.generation else { return }
                self.overlay.setLLMText(text)
            } catch {
                captureLog.error("LLM request failed: \(error.localizedDescription, privacy: .public)")
                guard token == self.generation else { return }
                self.overlay.failLLM(error.localizedDescription)
            }
        }
    }
}
