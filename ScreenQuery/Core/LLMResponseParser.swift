import Foundation

public enum LLMError: Error, Equatable, LocalizedError {
    case api(String)
    case malformed
    case empty

    public var errorDescription: String? {
        switch self {
        case .api(let message):
            return message
        case .malformed:
            return "The language model returned an unexpected response."
        case .empty:
            return "The language model returned an empty response."
        }
    }
}

public enum LLMResponseParser {
    /// Parses an OpenAI-compatible chat completion body.
    /// `message.content` may be a string or an array of text parts.
    public static func parse(data: Data) throws -> String {
        let object: Any
        do {
            object = try JSONSerialization.jsonObject(with: data)
        } catch {
            throw LLMError.malformed
        }
        guard let json = object as? [String: Any] else {
            throw LLMError.malformed
        }
        if let message = apiMessage(in: json) {
            throw LLMError.api(message)
        }
        guard let choices = json["choices"] as? [Any],
              let first = choices.first as? [String: Any],
              let message = first["message"] as? [String: Any] else {
            throw LLMError.malformed
        }
        let text = contentText(message["content"]).trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else {
            throw LLMError.empty
        }
        return text
    }

    public static func apiMessage(in json: [String: Any]) -> String? {
        if let error = json["error"] as? [String: Any] {
            if let message = error["message"] as? String, !message.isEmpty {
                return message
            }
            if let message = error["error"] as? String, !message.isEmpty {
                return message
            }
        }
        if let error = json["error"] as? String, !error.isEmpty {
            return error
        }
        return nil
    }

    private static func contentText(_ content: Any?) -> String {
        if let text = content as? String {
            return text
        }
        guard let parts = content as? [Any] else {
            return ""
        }
        return parts.compactMap { part in
            (part as? [String: Any])?["text"] as? String
        }.joined(separator: "\n")
    }
}
