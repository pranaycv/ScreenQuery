import CoreGraphics
import Foundation
import os

private let hotkeyLog = Logger(subsystem: "com.screenquery.app", category: "hotkey")

/// Session-wide listen-only event tap for the Shift+S+P chord.
///
/// Creating the tap requires Input Monitoring. Accessibility is also required
/// on some macOS versions. The tap does not swallow keystrokes.
final class GlobalHotkeyMonitor {
    var onChord: (() -> Void)?

    private let lock = NSLock()
    private var chord = HotkeyChord()
    /// Keycode of a recognized S/P key down, so key-up can release it even when
    /// the key-up event has no Unicode string.
    private var letterForKeyCode: [Int: String] = [:]
    private var thread: Thread?
    private var machPort: CFMachPort?
    private var runLoopSource: CFRunLoopSource?
    private var runLoop: CFRunLoop?
    private var isRunning = false
    private var stopRequested = false
    private var stopSemaphore: DispatchSemaphore?

    @discardableResult
    func start() -> Bool {
        stop()
        lock.lock()
        stopRequested = false
        lock.unlock()

        let ready = DispatchSemaphore(value: 0)
        let thread = Thread { [weak self] in
            self?.installAndRun(signal: ready)
        }
        thread.name = "ScreenQuery Hotkey"
        lock.lock()
        self.thread = thread
        lock.unlock()
        thread.start()
        ready.wait()

        lock.lock()
        let running = isRunning
        lock.unlock()
        if !running {
            hotkeyLog.error("Event tap was not created. Grant Input Monitoring and Accessibility, then recheck permissions.")
        }
        return running
    }

    func stop() {
        lock.lock()
        stopRequested = true
        let running = isRunning
        let loop = runLoop
        let port = machPort
        let semaphore = DispatchSemaphore(value: 0)
        if running {
            stopSemaphore = semaphore
        }
        lock.unlock()
        guard running else { return }

        if let port {
            CGEvent.tapEnable(tap: port, enable: false)
        }
        if let loop {
            CFRunLoopStop(loop)
        }
        _ = semaphore.wait(timeout: .now() + 2)
        chord.reset()
        letterForKeyCode.removeAll()
    }

    @discardableResult
    func restart() -> Bool {
        start()
    }

    fileprivate func handle(type: CGEventType, event: CGEvent) {
        if type == .tapDisabledByTimeout || type == .tapDisabledByUserInput {
            chord.reset()
            letterForKeyCode.removeAll()
            lock.lock()
            let port = machPort
            lock.unlock()
            if let port {
                CGEvent.tapEnable(tap: port, enable: true)
            }
            return
        }

        var fired = false
        switch type {
        case .keyDown:
            let code = Int(event.getIntegerValueField(.keyboardEventKeycode))
            let isRepeat = event.getIntegerValueField(.keyboardEventAutorepeat) != 0
            guard let letter = recognizedLetter(in: event, keyCode: code) else { return }
            letterForKeyCode[code] = letter
            fired = chord.keyDown(letter, isRepeat: isRepeat)
        case .keyUp:
            let code = Int(event.getIntegerValueField(.keyboardEventKeycode))
            guard let letter = letterForKeyCode.removeValue(forKey: code) else { return }
            fired = chord.keyUp(letter)
        case .flagsChanged:
            fired = chord.setShiftDown(event.flags.contains(.maskShift))
        default:
            fired = false
        }

        guard fired else { return }
        DispatchQueue.main.async { [weak self] in
            self?.onChord?()
        }
    }

    /// Letters S and P from the active layout. If a key-down has no Unicode
    /// string, fall back to the ANSI positions for those letters.
    private func recognizedLetter(in event: CGEvent, keyCode: Int) -> String? {
        let text = unicodeString(from: event).lowercased()
        if text == "s" || text == "p" {
            return text
        }
        if !text.isEmpty {
            return nil
        }
        if keyCode == 0x01 { return "s" }
        if keyCode == 0x23 { return "p" }
        return nil
    }

    private func unicodeString(from event: CGEvent) -> String {
        let maxCount = 8
        var buffer = [UniChar](repeating: 0, count: maxCount)
        var length = 0
        buffer.withUnsafeMutableBufferPointer { pointer in
            event.keyboardGetUnicodeString(
                maxStringLength: maxCount,
                actualStringLength: &length,
                unicodeString: pointer.baseAddress
            )
        }
        guard length > 0 else { return "" }
        return buffer.withUnsafeBufferPointer { pointer in
            guard let address = pointer.baseAddress else { return "" }
            return String(utf16CodeUnits: address, count: min(length, maxCount))
        }
    }

    private func installAndRun(signal: DispatchSemaphore) {
        let mask = eventMask(.keyDown) | eventMask(.keyUp) | eventMask(.flagsChanged)
        let userInfo = Unmanaged.passUnretained(self).toOpaque()
        guard let port = CGEvent.tapCreate(
            tap: .cgSessionEventTap,
            place: .headInsertEventTap,
            options: .listenOnly,
            eventsOfInterest: mask,
            callback: hotkeyTapCallback,
            userInfo: userInfo
        ) else {
            signal.signal()
            return
        }
        guard let source = CFMachPortCreateRunLoopSource(kCFAllocatorDefault, port, 0) else {
            signal.signal()
            return
        }

        let loop = CFRunLoopGetCurrent()
        CFRunLoopAddSource(loop, source, .commonModes)
        CGEvent.tapEnable(tap: port, enable: true)

        lock.lock()
        machPort = port
        runLoopSource = source
        runLoop = loop
        isRunning = true
        let shouldStop = stopRequested
        lock.unlock()
        signal.signal()

        // Poll as well as honoring CFRunLoopStop. A stop that arrives before
        // the loop is entered would otherwise be lost.
        if !shouldStop {
            while true {
                self.lock.lock()
                let stop = self.stopRequested
                self.lock.unlock()
                if stop { break }
                let result = CFRunLoopRunInMode(.defaultMode, 1.0, false)
                if result == .stopped || result == .finished {
                    self.lock.lock()
                    let stop = self.stopRequested
                    self.lock.unlock()
                    if stop { break }
                }
            }
        }

        CFRunLoopRemoveSource(loop, source, .commonModes)
        lock.lock()
        isRunning = false
        machPort = nil
        runLoopSource = nil
        runLoop = nil
        thread = nil
        let stopped = stopSemaphore
        stopSemaphore = nil
        lock.unlock()
        stopped?.signal()
    }
}

private func eventMask(_ type: CGEventType) -> CGEventMask {
    CGEventMask(1) << CGEventMask(type.rawValue)
}

private func hotkeyTapCallback(
    proxy: CGEventTapProxy,
    type: CGEventType,
    event: CGEvent,
    userInfo: UnsafeMutableRawPointer?
) -> Unmanaged<CGEvent>? {
    if let userInfo {
        let monitor = Unmanaged<GlobalHotkeyMonitor>.fromOpaque(userInfo).takeUnretainedValue()
        monitor.handle(type: type, event: event)
    }
    return Unmanaged.passUnretained(event)
}
