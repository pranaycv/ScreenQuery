import Foundation

public enum ScreenshotPathError: Error, Equatable {
    case tooManyCollisions
}

public enum PathDisplay {
    /// Renders a path with the home directory collapsed to `~`.
    public static func abbreviate(_ path: String, home: String) -> String {
        if path == home { return "~" }
        let prefix = home.hasSuffix("/") ? String(home.dropLast()) : home
        if path == prefix { return "~" }
        if path.hasPrefix(prefix + "/") {
            return "~" + path.dropFirst(prefix.count)
        }
        return path
    }
}

public enum ScreenshotPaths {
    public static func dayFolderName(for date: Date, timeZone: TimeZone = .current) -> String {
        formatter(dateFormat: "yyyy-MM-dd", timeZone: timeZone).string(from: date)
    }

    public static func fileName(for date: Date, timeZone: TimeZone = .current) -> String {
        let stamp = formatter(dateFormat: "yyyyMMdd-HHmmss-SSS", timeZone: timeZone).string(from: date)
        return "ScreenQuery-\(stamp).png"
    }

    /// Default saves under `~/ScreenQuery/<YYYY-MM-DD>/`.
    /// A chosen folder is used directly, without a date subfolder.
    public static func directory(
        now: Date,
        home: URL,
        useCustomFolder: Bool,
        customFolder: URL?,
        timeZone: TimeZone = .current
    ) -> URL {
        if useCustomFolder, let customFolder {
            return customFolder
        }
        return home
            .appendingPathComponent("ScreenQuery", isDirectory: true)
            .appendingPathComponent(dayFolderName(for: now, timeZone: timeZone), isDirectory: true)
    }

    public static func uniqueFileURL(
        in directory: URL,
        now: Date = Date(),
        fileManager: FileManager = .default,
        timeZone: TimeZone = .current
    ) throws -> URL {
        try fileManager.createDirectory(at: directory, withIntermediateDirectories: true)
        let name = fileName(for: now, timeZone: timeZone)
        let urlName = URL(fileURLWithPath: name)
        let stem = urlName.deletingPathExtension().lastPathComponent
        let ext = urlName.pathExtension
        var candidate = directory.appendingPathComponent(name)
        var suffix = 2
        while fileManager.fileExists(atPath: candidate.path) {
            candidate = directory.appendingPathComponent("\(stem)-\(suffix).\(ext)")
            suffix += 1
            if suffix > 10_000 {
                throw ScreenshotPathError.tooManyCollisions
            }
        }
        return candidate
    }

    private static func formatter(dateFormat: String, timeZone: TimeZone) -> DateFormatter {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = timeZone
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.dateFormat = dateFormat
        return formatter
    }
}
