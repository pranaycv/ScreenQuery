import XCTest
@testable import ScreenQueryCore

final class ScreenshotPathTests: XCTestCase {
    private let utc = TimeZone(secondsFromGMT: 0)!

    func testDefaultDirectoryNestsTheDateUnderScreenQuery() {
        let directory = ScreenshotPaths.directory(
            now: sampleDate,
            home: URL(fileURLWithPath: "/Users/ada", isDirectory: true),
            useCustomFolder: false,
            customFolder: URL(fileURLWithPath: "/tmp/ignored", isDirectory: true),
            timeZone: utc
        )
        XCTAssertEqual(normalized(directory), "/Users/ada/ScreenQuery/2026-10-01")
    }

    func testChosenFolderIsUsedWithoutADateSubfolder() {
        let chosen = URL(fileURLWithPath: "/Users/ada/Shots", isDirectory: true)
        let directory = ScreenshotPaths.directory(
            now: sampleDate,
            home: URL(fileURLWithPath: "/Users/ada", isDirectory: true),
            useCustomFolder: true,
            customFolder: chosen,
            timeZone: utc
        )
        XCTAssertEqual(directory, chosen)
    }

    func testMissingChosenFolderFallsBackToTheDefaultLayout() {
        let directory = ScreenshotPaths.directory(
            now: sampleDate,
            home: URL(fileURLWithPath: "/Users/ada", isDirectory: true),
            useCustomFolder: true,
            customFolder: nil,
            timeZone: utc
        )
        XCTAssertEqual(normalized(directory), "/Users/ada/ScreenQuery/2026-10-01")
    }

    func testFileNameIsTimestampedPNG() {
        let name = ScreenshotPaths.fileName(for: sampleDate, timeZone: utc)
        XCTAssertTrue(name.hasPrefix("ScreenQuery-20261001-223507-"))
        XCTAssertTrue(name.hasSuffix(".png"))
        XCTAssertNotNil(name.range(of: #"^ScreenQuery-\d{8}-\d{6}-\d{3}\.png$"#, options: .regularExpression))
    }

    func testUniqueFileURLAppendsASuffixWhenTheNameExists() throws {
        let root = URL(fileURLWithPath: NSTemporaryDirectory(), isDirectory: true)
            .appendingPathComponent("ScreenQueryTests-\(UUID().uuidString)", isDirectory: true)
        let manager = FileManager.default
        let first = try ScreenshotPaths.uniqueFileURL(in: root, now: sampleDate, fileManager: manager, timeZone: utc)
        try Data("png".utf8).write(to: first)
        let second = try ScreenshotPaths.uniqueFileURL(in: root, now: sampleDate, fileManager: manager, timeZone: utc)
        XCTAssertNotEqual(first, second)
        XCTAssertTrue(second.lastPathComponent.contains("-2.png"))
        try? manager.removeItem(at: root)
    }

    func testAbbreviateCollapsesTheHomeDirectory() {
        XCTAssertEqual(PathDisplay.abbreviate("/Users/ada/ScreenQuery/2026-10-01/a.png", home: "/Users/ada"), "~/ScreenQuery/2026-10-01/a.png")
        XCTAssertEqual(PathDisplay.abbreviate("/Users/ada", home: "/Users/ada"), "~")
        XCTAssertEqual(PathDisplay.abbreviate("/tmp/shots/a.png", home: "/Users/ada"), "/tmp/shots/a.png")
    }

    private func normalized(_ url: URL) -> String {
        var path = url.path
        if path.count > 1, path.hasSuffix("/") {
            path.removeLast()
        }
        return path
    }

    private var sampleDate: Date {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = utc
        var components = DateComponents()
        components.calendar = calendar
        components.timeZone = utc
        components.year = 2026
        components.month = 10
        components.day = 1
        components.hour = 22
        components.minute = 35
        components.second = 7
        components.nanosecond = 0
        return calendar.date(from: components)!
    }
}
