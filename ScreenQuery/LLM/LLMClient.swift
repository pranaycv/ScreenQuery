import CoreGraphics
import Foundation

struct LLMRequestSettings: Sendable {
    var baseURL: String
    var model: String
    var apiKey: String
    var prompt: String
}

enum LLMClientError: LocalizedError {
    case invalidEndpoint
    case encodingFailed
    case transport(String)
    case status(Int, String)

    var errorDescription: String? {
        switch self {
        case .invalidEndpoint:
            return "The model base URL is not a valid http or https URL."
        case .encodingFailed:
            return "Couldn't encode the screenshot for the model."
        case .transport(let message):
            return "Couldn't reach the model. \(message)"
        case .status(let code, let message):
            if code == 401 {
                return "The API key was rejected. \(message)"
            }
            if code == 404 {
                return "The model or endpoint was not found. \(message)"
            }
            return "The model request failed (\(code)). \(message)"
        }
    }
}

struct LLMClient {
    var session: URLSession = {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.timeoutIntervalForRequest = 60
        configuration.timeoutIntervalForResource = 90
        return URLSession(configuration: configuration)
    }()

    func explain(image: CGImage, settings: LLMRequestSettings) async throws -> String {
        guard let url = LLMEndpoint.chatCompletionsURL(baseURL: settings.baseURL) else {
            throw LLMClientError.invalidEndpoint
        }
        guard let jpeg = ImageEncoder.llmJPEG(from: image) else {
            throw LLMClientError.encodingFailed
        }
        let body: [String: Any] = [
            "model": settings.model,
            "temperature": 0.2,
            "max_tokens": 1000,
            "messages": [
                [
                    "role": "user",
                    "content": [
                        ["type": "text", "text": settings.prompt],
                        [
                            "type": "image_url",
                            "image_url": ["url": "data:image/jpeg;base64,\(jpeg.base64EncodedString())"]
                        ]
                    ]
                ]
            ]
        ]
        let payload = try JSONSerialization.data(withJSONObject: body)
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("Bearer \(settings.apiKey)", forHTTPHeaderField: "Authorization")
        request.setValue("ScreenQuery/1.0", forHTTPHeaderField: "User-Agent")
        request.httpBody = payload

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch {
            throw LLMClientError.transport(error.localizedDescription)
        }

        if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
            throw LLMClientError.status(http.statusCode, failureDetail(from: data))
        }
        do {
            return try LLMResponseParser.parse(data: data)
        } catch let error as LLMError {
            throw error
        } catch {
            throw LLMError.malformed
        }
    }

    private func failureDetail(from data: Data) -> String {
        if let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let message = LLMResponseParser.apiMessage(in: object) {
            return message
        }
        let snippet = String(data: data.prefix(240), encoding: .utf8)?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return snippet.isEmpty ? "The server returned an error." : snippet
    }
}
