import CoreGraphics
import Foundation

enum SaveError: LocalizedError {
    case encodingFailed
    case writeFailed(String)

    var errorDescription: String? {
        switch self {
        case .encodingFailed:
            return "Couldn't encode the screenshot as a PNG."
        case .writeFailed(let message):
            return "Couldn't write the screenshot. \(message)"
        }
    }
}

struct SaveOutcome {
    var url: URL
    var note: String?
}

@MainActor
enum ScreenshotSaver {
    static func save(_ image: CGImage, settings: SettingsStore, now: Date = Date()) throws -> SaveOutcome {
        let home = FileManager.default.homeDirectoryForCurrentUser
        var note: String?
        var useCustom = settings.useCustomFolder
        let custom = useCustom ? settings.prepareCustomFolderAccess() : nil
        if useCustom && custom == nil {
            useCustom = false
            note = "The chosen folder is unavailable, so this screenshot was saved to ~/ScreenQuery."
        }
        let directory = ScreenshotPaths.directory(
            now: now,
            home: home,
            useCustomFolder: useCustom,
            customFolder: custom
        )
        guard let png = ImageEncoder.pngData(from: image) else {
            throw SaveError.encodingFailed
        }
        let url = try ScreenshotPaths.uniqueFileURL(in: directory, now: now)
        do {
            try png.write(to: url, options: .atomic)
        } catch {
            throw SaveError.writeFailed(error.localizedDescription)
        }
        return SaveOutcome(url: url, note: note)
    }
}
