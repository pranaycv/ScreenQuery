import Foundation

public enum LLMEndpoint {
    /// Builds an OpenAI-compatible `chat/completions` URL from a user-entered base.
    ///
    /// Accepts either a base such as `https://api.openai.com/v1` or a full
    /// `.../chat/completions` URL. Query items are preserved.
    public static func chatCompletionsURL(baseURL: String) -> URL? {
        let trimmed = baseURL.trimmingCharacters(in: .whitespacesAndNewlines)
        guard var components = URLComponents(string: trimmed),
              let scheme = components.scheme?.lowercased(),
              scheme == "http" || scheme == "https",
              let host = components.host,
              !host.isEmpty else {
            return nil
        }
        components.scheme = scheme
        var path = components.path
        while path.count > 1 && path.hasSuffix("/") {
            path.removeLast()
        }
        if !path.hasSuffix("/chat/completions") {
            if path.isEmpty || path == "/" {
                path = "/chat/completions"
            } else {
                path += "/chat/completions"
            }
        }
        components.path = path
        return components.url
    }
}
