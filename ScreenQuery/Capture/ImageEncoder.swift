import CoreGraphics
import Foundation
import ImageIO
import UniformTypeIdentifiers

enum ImageEncoder {
    static func pngData(from image: CGImage) -> Data? {
        let data = NSMutableData()
        guard let destination = CGImageDestinationCreateWithData(
            data as CFMutableData,
            UTType.png.identifier as CFString,
            1,
            nil
        ) else {
            return nil
        }
        CGImageDestinationAddImage(destination, image, nil)
        guard CGImageDestinationFinalize(destination) else { return nil }
        return data as Data
    }

    /// JPEG small enough to send to a vision model, preferring readable text.
    static func llmJPEG(from image: CGImage) -> Data? {
        let attempts: [(Int, CGFloat)] = [(1920, 0.82), (1600, 0.72), (1280, 0.64)]
        var last: Data?
        for (dimension, quality) in attempts {
            guard let data = jpegData(from: image, maxDimension: dimension, quality: quality) else {
                continue
            }
            last = data
            if data.count <= 4_500_000 {
                return data
            }
        }
        return last
    }

    static func jpegData(from image: CGImage, maxDimension: Int, quality: CGFloat) -> Data? {
        let scaled = resize(image, maxDimension: maxDimension) ?? image
        let data = NSMutableData()
        guard let destination = CGImageDestinationCreateWithData(
            data as CFMutableData,
            UTType.jpeg.identifier as CFString,
            1,
            nil
        ) else {
            return nil
        }
        let properties = [kCGImageDestinationLossyCompressionQuality: quality] as CFDictionary
        CGImageDestinationAddImage(destination, scaled, properties)
        guard CGImageDestinationFinalize(destination) else { return nil }
        return data as Data
    }

    static func resize(_ image: CGImage, maxDimension: Int) -> CGImage? {
        let width = image.width
        let height = image.height
        let longest = max(width, height)
        guard longest > maxDimension, maxDimension > 0 else { return image }

        let scale = CGFloat(maxDimension) / CGFloat(longest)
        let newWidth = max(1, Int((CGFloat(width) * scale).rounded()))
        let newHeight = max(1, Int((CGFloat(height) * scale).rounded()))
        guard let colorSpace = CGColorSpace(name: CGColorSpace.sRGB) else { return nil }
        guard let context = CGContext(
            data: nil,
            width: newWidth,
            height: newHeight,
            bitsPerComponent: 8,
            bytesPerRow: 0,
            space: colorSpace,
            bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
        ) else {
            return nil
        }
        context.interpolationQuality = .high
        context.draw(image, in: CGRect(x: 0, y: 0, width: newWidth, height: newHeight))
        return context.makeImage()
    }
}
