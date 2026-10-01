import CoreGraphics
import Foundation
import ScreenCaptureKit

enum CaptureError: LocalizedError {
    case permissionDenied
    case noDisplay
    case failed(String)

    var errorDescription: String? {
        switch self {
        case .permissionDenied:
            return "Screen Recording permission is required. Enable ScreenQuery in System Settings → Privacy & Security → Screen Recording, then try the hotkey again. macOS often requires quitting and reopening the app after you grant access."
        case .noDisplay:
            return "No display was available to capture."
        case .failed(let message):
            return message
        }
    }
}

enum ScreenshotService {
    /// Captures every active display and stitches them into one image.
    /// A single display is returned as-is. ScreenQuery's own windows are excluded.
    static func capture() async throws -> CGImage {
        let content: SCShareableContent
        do {
            content = try await SCShareableContent.excludingDesktopWindows(
                false,
                onScreenWindowsOnly: true
            )
        } catch {
            if !CGPreflightScreenCaptureAccess() {
                throw CaptureError.permissionDenied
            }
            throw CaptureError.failed(error.localizedDescription)
        }

        let displays = content.displays.sorted { lhs, rhs in
            if lhs.frame.minX != rhs.frame.minX {
                return lhs.frame.minX < rhs.frame.minX
            }
            return lhs.frame.minY < rhs.frame.minY
        }
        guard !displays.isEmpty else {
            throw CaptureError.noDisplay
        }

        var captured: [CapturedDisplay] = []
        var lastError: Error?
        for display in displays {
            do {
                let image = try await capture(display: display, content: content)
                captured.append(CapturedDisplay(image: image, frame: display.frame))
            } catch {
                lastError = error
            }
        }
        guard !captured.isEmpty else {
            if !CGPreflightScreenCaptureAccess() {
                throw CaptureError.permissionDenied
            }
            throw CaptureError.failed(lastError?.localizedDescription ?? "Screen capture failed.")
        }
        if captured.count == 1 {
            return captured[0].image
        }
        return composite(captured) ?? largestImage(in: captured)
    }

    private static func capture(display: SCDisplay, content: SCShareableContent) async throws -> CGImage {
        let bundleID = Bundle.main.bundleIdentifier
        let excluded = content.applications.filter { $0.bundleIdentifier == bundleID }
        let filter: SCContentFilter
        if excluded.isEmpty {
            filter = SCContentFilter(display: display, excludingWindows: [])
        } else {
            filter = SCContentFilter(
                display: display,
                excludingApplications: excluded,
                exceptingWindows: []
            )
        }
        let configuration = SCStreamConfiguration()
        configuration.width = display.width
        configuration.height = display.height
        configuration.showsCursor = true
        configuration.capturesAudio = false
        return try await SCScreenshotManager.captureImage(
            contentFilter: filter,
            configuration: configuration
        )
    }

    private static func composite(_ items: [CapturedDisplay]) -> CGImage? {
        let usable = items.filter { $0.frame.width > 1 && $0.frame.height > 1 && $0.image.width > 0 }
        guard usable.count > 1 else { return usable.first?.image }

        let minX = usable.map(\.frame.minX).min() ?? 0
        let minY = usable.map(\.frame.minY).min() ?? 0
        let maxX = usable.map(\.frame.maxX).max() ?? 0
        let maxY = usable.map(\.frame.maxY).max() ?? 0
        let pointsWidth = maxX - minX
        let pointsHeight = maxY - minY
        guard pointsWidth > 1, pointsHeight > 1 else { return nil }

        let scale = usable.map { CGFloat($0.image.width) / $0.frame.width }.max() ?? 2
        guard scale > 0 else { return nil }
        let pixelWidth = max(1, Int((pointsWidth * scale).rounded()))
        let pixelHeight = max(1, Int((pointsHeight * scale).rounded()))
        guard let colorSpace = CGColorSpace(name: CGColorSpace.sRGB),
              let context = CGContext(
                data: nil,
                width: pixelWidth,
                height: pixelHeight,
                bitsPerComponent: 8,
                bytesPerRow: 0,
                space: colorSpace,
                bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
              ) else {
            return nil
        }
        context.interpolationQuality = .high
        if let fill = CGColor(colorSpace: colorSpace, components: [0, 0, 0, 1]) {
            context.setFillColor(fill)
            context.fill(CGRect(x: 0, y: 0, width: pixelWidth, height: pixelHeight))
        }

        // Display frames and CGContext are both Y-up, origin bottom-left.
        for item in usable {
            let rect = CGRect(
                x: (item.frame.minX - minX) * scale,
                y: (item.frame.minY - minY) * scale,
                width: item.frame.width * scale,
                height: item.frame.height * scale
            )
            context.draw(item.image, in: rect)
        }
        return context.makeImage()
    }

    private static func largestImage(in items: [CapturedDisplay]) -> CGImage {
        let largest = items.max { lhs, rhs in
            lhs.image.width * lhs.image.height < rhs.image.width * rhs.image.height
        }
        return largest?.image ?? items[0].image
    }
}

private struct CapturedDisplay {
    let image: CGImage
    let frame: CGRect
}
