import XCTest
@testable import ScreenQueryCore

final class HotkeyChordTests: XCTestCase {
    func testFiresWhenShiftAndBothLettersAreDown() {
        var chord = HotkeyChord()
        XCTAssertFalse(chord.setShiftDown(true))
        XCTAssertFalse(chord.keyDown("s", isRepeat: false))
        XCTAssertTrue(chord.keyDown("p", isRepeat: false))
        XCTAssertTrue(chord.isActive)
    }

    func testOrderOfLettersDoesNotMatter() {
        var chord = HotkeyChord()
        XCTAssertFalse(chord.keyDown("P", isRepeat: false))
        XCTAssertFalse(chord.setShiftDown(true))
        XCTAssertTrue(chord.keyDown("S", isRepeat: false))
    }

    func testDoesNotFireWithoutShift() {
        var chord = HotkeyChord()
        XCTAssertFalse(chord.keyDown("s", isRepeat: false))
        XCTAssertFalse(chord.keyDown("p", isRepeat: false))
        XCTAssertFalse(chord.isActive)
    }

    func testDoesNotRepeatWhileHeld() {
        var chord = HotkeyChord()
        XCTAssertFalse(chord.setShiftDown(true))
        XCTAssertFalse(chord.keyDown("s", isRepeat: false))
        XCTAssertTrue(chord.keyDown("p", isRepeat: false))
        XCTAssertFalse(chord.keyDown("p", isRepeat: true))
        XCTAssertFalse(chord.keyDown("s", isRepeat: true))
        XCTAssertFalse(chord.setShiftDown(true))
    }

    func testFiresAgainAfterRelease() {
        var chord = HotkeyChord()
        XCTAssertTrue(activate(&chord))
        _ = chord.keyUp("s")
        XCTAssertFalse(chord.isActive)
        XCTAssertTrue(chord.keyDown("s", isRepeat: false))
    }

    func testReleasingShiftAllowsAnotherPress() {
        var chord = HotkeyChord()
        XCTAssertTrue(activate(&chord))
        XCTAssertFalse(chord.setShiftDown(false))
        XCTAssertFalse(chord.isActive)
        XCTAssertTrue(chord.setShiftDown(true))
    }

    func testUnrelatedLetterDoesNotActivateOrRepeat() {
        var chord = HotkeyChord()
        XCTAssertFalse(chord.setShiftDown(true))
        XCTAssertFalse(chord.keyDown("a", isRepeat: false))
        XCTAssertFalse(chord.keyDown("s", isRepeat: false))
        XCTAssertTrue(chord.keyDown("p", isRepeat: false))
        XCTAssertFalse(chord.keyDown("x", isRepeat: false))
        XCTAssertTrue(chord.isActive)
    }

    func testResetClearsAHeldChord() {
        var chord = HotkeyChord()
        XCTAssertTrue(activate(&chord))
        chord.reset()
        XCTAssertFalse(chord.isActive)
        XCTAssertFalse(chord.keyDown("p", isRepeat: false))
        XCTAssertTrue(activate(&chord))
    }

    private func activate(_ chord: inout HotkeyChord) -> Bool {
        _ = chord.setShiftDown(true)
        _ = chord.keyDown("s", isRepeat: false)
        return chord.keyDown("p", isRepeat: false)
    }
}
