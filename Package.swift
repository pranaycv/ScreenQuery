// swift-tools-version:5.9
import PackageDescription

// Logic tests for the macOS app. The app target compiles these sources
// directly; this package exists so `swift test` can run without Xcode.
let package = Package(
    name: "ScreenQueryCore",
    products: [
        .library(name: "ScreenQueryCore", targets: ["ScreenQueryCore"])
    ],
    targets: [
        .target(
            name: "ScreenQueryCore",
            path: "ScreenQuery/Core"
        ),
        .testTarget(
            name: "ScreenQueryCoreTests",
            dependencies: ["ScreenQueryCore"],
            path: "Tests/ScreenQueryCoreTests"
        )
    ],
    swiftLanguageVersions: [.v5]
)
