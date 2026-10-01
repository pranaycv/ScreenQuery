import AppKit
import SwiftUI

@MainActor
final class OverlayModel: ObservableObject {
    @Published var headline = "ScreenQuery"
    @Published var savedPath: String?
    @Published var savedURL: URL?
    @Published var note: String?
    @Published var llmText: String?
    @Published var llmPending = false
    @Published var errors: [String] = []
    @Published var showProgress = false
    @Published var actionTitle: String?
    @Published var copied = false
}

@MainActor
final class StatusOverlayController {
    let model = OverlayModel()
    var dismissSeconds: () -> Int = { 12 }

    private var panel: OverlayPanel?
    private var dismissTask: Task<Void, Never>?
    private var safetyTask: Task<Void, Never>?
    private var copyReset: Task<Void, Never>?
    private var actionHandler: (() -> Void)?
    private var dismissing = false
    private var suppressPresentation = false

    func beginCapture() {
        suppressPresentation = false
        model.headline = "Capturing the screen…"
        model.savedPath = nil
        model.savedURL = nil
        model.note = nil
        model.llmText = nil
        model.llmPending = false
        model.errors = []
        model.showProgress = true
        model.actionTitle = nil
        model.copied = false
        actionHandler = nil
        present()
        scheduleSafety()
    }

    func setSaved(url: URL, note: String?) {
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        model.savedURL = url
        model.savedPath = PathDisplay.abbreviate(url.path, home: home)
        model.note = note
        model.showProgress = model.llmPending
        if !model.llmPending {
            model.headline = "Screenshot saved"
            scheduleDismissIfIdle()
        }
        present()
    }

    func setLLMPending() {
        model.llmPending = true
        model.showProgress = true
        if model.savedPath == nil {
            model.headline = "Asking the model…"
        }
        dismissTask?.cancel()
        present()
    }

    func setLLMText(_ text: String) {
        model.llmPending = false
        model.showProgress = false
        model.llmText = text
        model.headline = model.savedPath == nil ? "Response" : "Screenshot saved"
        cancelSafety()
        scheduleDismissIfIdle()
        present()
    }

    func addError(_ message: String) {
        model.errors.append(message)
        model.showProgress = false
        if model.headline == "Capturing the screen…" {
            model.headline = "Something went wrong"
        }
        present()
    }

    func failLLM(_ message: String) {
        model.llmPending = false
        model.showProgress = false
        model.headline = model.savedPath == nil ? "Something went wrong" : "Screenshot saved"
        addError(message)
        cancelSafety()
        scheduleDismissIfIdle()
        present()
    }

    func showStandalone(
        headline: String,
        detail: String,
        isError: Bool,
        actionTitle: String? = nil,
        action: (() -> Void)? = nil
    ) {
        model.headline = headline
        model.savedPath = nil
        model.savedURL = nil
        model.note = isError ? nil : detail
        model.llmText = nil
        model.llmPending = false
        model.showProgress = false
        model.errors = isError ? [detail] : []
        model.copied = false
        model.actionTitle = actionTitle
        actionHandler = action
        present()
        scheduleSafety()
        scheduleDismissIfIdle()
    }

    func setAction(title: String, action: @escaping () -> Void) {
        model.actionTitle = title
        actionHandler = action
        present()
    }

    func finishPendingWork() {
        model.showProgress = false
        model.llmPending = false
        if model.errors.isEmpty, model.savedPath != nil {
            model.headline = "Screenshot saved"
        }
        scheduleDismissIfIdle()
        relayoutSoon()
    }

    func dismiss(byUser: Bool = false) {
        if byUser {
            suppressPresentation = true
        }
        guard let panel, panel.isVisible, !dismissing else { return }
        dismissing = true
        dismissTask?.cancel()
        safetyTask?.cancel()
        NSAnimationContext.runAnimationGroup({ context in
            context.duration = 0.18
            panel.animator().alphaValue = 0
        }, completionHandler: {
            Task { @MainActor in
                panel.orderOut(nil)
                panel.alphaValue = 1
                self.dismissing = false
            }
        })
    }

    private func present() {
        guard !suppressPresentation else { return }
        let panel = ensurePanel()
        dismissing = false
        relayout()
        relayoutSoon()
        guard !panel.isVisible else {
            panel.alphaValue = 1
            return
        }
        panel.alphaValue = 0
        panel.orderFrontRegardless()
        NSAnimationContext.runAnimationGroup { context in
            context.duration = 0.16
            panel.animator().alphaValue = 1
        }
    }

    private func ensurePanel() -> OverlayPanel {
        if let panel { return panel }
        let root = StatusOverlayView(
            model: model,
            onDismiss: { [weak self] in self?.dismiss(byUser: true) },
            onReveal: { [weak self] in self?.revealSavedFile() },
            onCopy: { [weak self] in self?.copyResponse() },
            onAction: { [weak self] in self?.actionHandler?() }
        )
        let hosting = NSHostingController(rootView: root)
        let panel = OverlayPanel(
            contentRect: NSRect(x: 0, y: 0, width: 428, height: 180),
            styleMask: [.borderless, .nonactivatingPanel],
            backing: .buffered,
            defer: false
        )
        panel.contentViewController = hosting
        panel.isFloatingPanel = true
        panel.level = .floating
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .ignoresCycle]
        panel.isOpaque = false
        panel.backgroundColor = .clear
        panel.hasShadow = true
        panel.hidesOnDeactivate = false
        panel.becomesKeyOnlyIfNeeded = true
        panel.isMovable = false
        panel.worksWhenModal = true
        panel.sharingType = .none
        panel.isExcludedFromWindowsMenu = true
        panel.title = "ScreenQuery"
        panel.animationBehavior = .none
        self.panel = panel
        return panel
    }

    private func revealSavedFile() {
        guard let url = model.savedURL else { return }
        NSWorkspace.shared.activateFileViewerSelecting([url])
    }

    private func copyResponse() {
        guard let text = model.llmText, !text.isEmpty else { return }
        let pasteboard = NSPasteboard.general
        pasteboard.clearContents()
        pasteboard.setString(text, forType: .string)
        model.copied = true
        copyReset?.cancel()
        copyReset = Task { [weak self] in
            try? await Task.sleep(nanoseconds: 1_500_000_000)
            self?.model.copied = false
        }
    }

    private func scheduleDismissIfIdle() {
        dismissTask?.cancel()
        guard !model.llmPending else { return }
        let seconds = max(4, dismissSeconds())
        dismissTask = Task { [weak self] in
            try? await Task.sleep(nanoseconds: UInt64(seconds) * 1_000_000_000)
            guard !Task.isCancelled, let self else { return }
            if self.pointerInside {
                self.scheduleDismissIfIdle()
                return
            }
            self.dismiss()
        }
    }

    private func scheduleSafety() {
        safetyTask?.cancel()
        safetyTask = Task { [weak self] in
            try? await Task.sleep(nanoseconds: 90 * 1_000_000_000)
            guard !Task.isCancelled else { return }
            self?.dismiss()
        }
    }

    private func cancelSafety() {
        safetyTask?.cancel()
        safetyTask = nil
    }

    private var pointerInside: Bool {
        guard let panel else { return false }
        return panel.frame.contains(NSEvent.mouseLocation)
    }

    private func relayoutSoon() {
        DispatchQueue.main.async { [weak self] in
            self?.relayout()
        }
    }

    private func relayout() {
        guard let panel, let hosting = panel.contentViewController else { return }
        hosting.view.layoutSubtreeIfNeeded()
        let fitted = hosting.view.fittingSize
        let width = max(fitted.width, 428)
        let height = min(max(fitted.height, 96), 560)
        panel.setContentSize(NSSize(width: width, height: height))
        position(panel)
    }

    private func position(_ panel: NSWindow) {
        let mouse = NSEvent.mouseLocation
        let screen = NSScreen.screens.first(where: { $0.frame.contains(mouse) }) ?? NSScreen.main
        guard let screen else { return }
        let visible = screen.visibleFrame
        let size = panel.frame.size
        let origin = NSPoint(
            x: visible.maxX - size.width - 12,
            y: visible.maxY - size.height - 12
        )
        panel.setFrameOrigin(origin)
    }
}

final class OverlayPanel: NSPanel {
    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { false }
}
