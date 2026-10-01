import AppKit
import Foundation

@MainActor
final class SettingsStore: ObservableObject {
    static let defaultBaseURL = "https://api.openai.com/v1"
    static let defaultModel = "gpt-4o"
    static let defaultPrompt = """
    Look at this screenshot. If it contains a question, answer it. If it contains a problem, error, or task, solve or explain it. Otherwise explain the most relevant content on screen. Be concise and accurate. Use plain text.
    """

    private enum Key {
        static let saveEnabled = "saveEnabled"
        static let llmEnabled = "llmEnabled"
        static let useCustomFolder = "useCustomFolder"
        static let customFolderPath = "customFolderPath"
        static let customFolderBookmark = "customFolderBookmark"
        static let llmBaseURL = "llmBaseURL"
        static let llmModel = "llmModel"
        static let llmPrompt = "llmPrompt"
        static let overlayDismissSeconds = "overlayDismissSeconds"
    }

    private let defaults: UserDefaults
    private var scopedFolder: URL?

    @Published var saveEnabled: Bool {
        didSet { defaults.set(saveEnabled, forKey: Key.saveEnabled) }
    }
    @Published var llmEnabled: Bool {
        didSet { defaults.set(llmEnabled, forKey: Key.llmEnabled) }
    }
    @Published var useCustomFolder: Bool {
        didSet { defaults.set(useCustomFolder, forKey: Key.useCustomFolder) }
    }
    @Published var customFolderPath: String? {
        didSet { persist(customFolderPath, forKey: Key.customFolderPath) }
    }
    @Published var customFolderBookmark: Data? {
        didSet { persist(customFolderBookmark, forKey: Key.customFolderBookmark) }
    }
    @Published var llmBaseURL: String {
        didSet { defaults.set(llmBaseURL, forKey: Key.llmBaseURL) }
    }
    @Published var llmModel: String {
        didSet { defaults.set(llmModel, forKey: Key.llmModel) }
    }
    @Published var llmPrompt: String {
        didSet { defaults.set(llmPrompt, forKey: Key.llmPrompt) }
    }
    @Published var overlayDismissSeconds: Int {
        didSet { defaults.set(overlayDismissSeconds, forKey: Key.overlayDismissSeconds) }
    }

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        saveEnabled = defaults.object(forKey: Key.saveEnabled) as? Bool ?? true
        llmEnabled = defaults.object(forKey: Key.llmEnabled) as? Bool ?? false
        useCustomFolder = defaults.object(forKey: Key.useCustomFolder) as? Bool ?? false
        customFolderPath = defaults.string(forKey: Key.customFolderPath)
        customFolderBookmark = defaults.data(forKey: Key.customFolderBookmark)
        llmBaseURL = defaults.string(forKey: Key.llmBaseURL) ?? Self.defaultBaseURL
        llmModel = defaults.string(forKey: Key.llmModel) ?? Self.defaultModel
        llmPrompt = defaults.string(forKey: Key.llmPrompt) ?? Self.defaultPrompt
        let storedSeconds = defaults.object(forKey: Key.overlayDismissSeconds) as? Int ?? 12
        overlayDismissSeconds = min(120, max(4, storedSeconds))
    }

    var folderDescription: String {
        if useCustomFolder {
            if let url = resolvedCustomFolderURL() {
                return PathDisplay.abbreviate(
                    url.path,
                    home: FileManager.default.homeDirectoryForCurrentUser.path
                )
            }
            if let customFolderPath, !customFolderPath.isEmpty {
                return "Unavailable: \(customFolderPath)"
            }
            return "No folder selected"
        }
        let day = ScreenshotPaths.dayFolderName(for: Date())
        return "~/ScreenQuery/\(day)/"
    }

    var effectivePrompt: String {
        let trimmed = llmPrompt.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? Self.defaultPrompt : trimmed
    }

    func chooseFolder() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        panel.canCreateDirectories = true
        panel.allowsMultipleSelection = false
        panel.prompt = "Choose"
        panel.message = "Screenshots are written directly into this folder."
        panel.directoryURL = resolvedCustomFolderURL()
            ?? FileManager.default.homeDirectoryForCurrentUser
        guard panel.runModal() == .OK, let url = panel.url else { return }
        customFolderPath = url.path
        customFolderBookmark = Self.bookmarkData(for: url)
        useCustomFolder = true
    }

    func revealSaveFolder() {
        let home = FileManager.default.homeDirectoryForCurrentUser
        let custom = useCustomFolder ? resolvedCustomFolderURL() : nil
        let directory = ScreenshotPaths.directory(
            now: Date(),
            home: home,
            useCustomFolder: custom != nil,
            customFolder: custom
        )
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        NSWorkspace.shared.open(directory)
    }

    /// Resolves the chosen folder without starting a security scope.
    /// Safe to call while rendering settings.
    func resolvedCustomFolderURL() -> URL? {
        if let data = customFolderBookmark {
            let attempts: [URL.BookmarkResolutionOptions] = [
                .withSecurityScope,
                URL.BookmarkResolutionOptions(rawValue: 0)
            ]
            for option in attempts {
                var stale = false
                if let url = try? URL(
                    resolvingBookmarkData: data,
                    options: option,
                    relativeTo: nil,
                    bookmarkDataIsStale: &stale
                ), Self.isDirectory(url) {
                    return url
                }
            }
        }
        if let customFolderPath, !customFolderPath.isEmpty {
            let url = URL(fileURLWithPath: customFolderPath, isDirectory: true)
            if Self.isDirectory(url) {
                return url
            }
        }
        return nil
    }

    /// Starts security-scoped access for the chosen folder before writing.
    func prepareCustomFolderAccess() -> URL? {
        guard let url = resolvedCustomFolderURL() else { return nil }
        if scopedFolder?.path != url.path {
            scopedFolder?.stopAccessingSecurityScopedResource()
            scopedFolder = nil
            if url.startAccessingSecurityScopedResource() {
                scopedFolder = url
            }
        }
        return url
    }

    private func persist(_ value: Any?, forKey key: String) {
        if let value {
            defaults.set(value, forKey: key)
        } else {
            defaults.removeObject(forKey: key)
        }
    }

    private static func isDirectory(_ url: URL) -> Bool {
        var isDirectory: ObjCBool = false
        return FileManager.default.fileExists(atPath: url.path, isDirectory: &isDirectory) && isDirectory.boolValue
    }

    private static func bookmarkData(for url: URL) -> Data? {
        if let data = try? url.bookmarkData(
            options: [.withSecurityScope],
            includingResourceValuesForKeys: nil,
            relativeTo: nil
        ) {
            return data
        }
        return try? url.bookmarkData(
            options: [],
            includingResourceValuesForKeys: nil,
            relativeTo: nil
        )
    }
}
