import Foundation

/// Tracks a simultaneous Shift+S+P chord.
///
/// Pass lowercase letters `"s"` and `"p"` (the monitor resolves them from the
/// active keyboard layout). The chord fires once when Shift is held and both
/// letters are down, and it does not repeat until one of them is released.
public struct HotkeyChord: Equatable {
    public private(set) var isActive = false
    private var pressed: Set<String> = []
    private var shiftDown = false

    public init() {}

    /// Returns true only on the transition into the chord.
    @discardableResult
    public mutating func keyDown(_ token: String, isRepeat: Bool) -> Bool {
        guard !isRepeat else { return false }
        let letter = token.lowercased()
        guard letter == "s" || letter == "p" else { return false }
        pressed.insert(letter)
        return activateIfNeeded()
    }

    @discardableResult
    public mutating func keyUp(_ token: String) -> Bool {
        pressed.remove(token.lowercased())
        deactivateIfBroken()
        return false
    }

    /// Returns true only on the transition into the chord.
    @discardableResult
    public mutating func setShiftDown(_ down: Bool) -> Bool {
        shiftDown = down
        if down {
            return activateIfNeeded()
        }
        deactivateIfBroken()
        return false
    }

    public mutating func reset() {
        pressed.removeAll()
        shiftDown = false
        isActive = false
    }

    private var chordHeld: Bool {
        shiftDown && pressed.contains("s") && pressed.contains("p")
    }

    private mutating func activateIfNeeded() -> Bool {
        guard chordHeld, !isActive else { return false }
        isActive = true
        return true
    }

    private mutating func deactivateIfBroken() {
        if !chordHeld {
            isActive = false
        }
    }
}
