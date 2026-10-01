import XCTest
@testable import ScreenQueryCore

final class LLMParsingTests: XCTestCase {
    func testAppendsChatCompletionsToABaseURL() {
        let url = LLMEndpoint.chatCompletionsURL(baseURL: "https://api.openai.com/v1")
        XCTAssertEqual(url?.absoluteString, "https://api.openai.com/v1/chat/completions")
    }

    func testTrimsATrailingSlashAndKeepsAnExistingCompletionsPath() {
        XCTAssertEqual(
            LLMEndpoint.chatCompletionsURL(baseURL: " https://api.openai.com/v1/ ")?.absoluteString,
            "https://api.openai.com/v1/chat/completions"
        )
        XCTAssertEqual(
            LLMEndpoint.chatCompletionsURL(baseURL: "https://example.com/v1/chat/completions/")?.absoluteString,
            "https://example.com/v1/chat/completions"
        )
    }

    func testAcceptsLocalHTTPAndPreservesTheQuery() {
        let url = LLMEndpoint.chatCompletionsURL(baseURL: "http://127.0.0.1:8080/v1?x=1")
        XCTAssertEqual(url?.scheme, "http")
        XCTAssertEqual(url?.host, "127.0.0.1")
        XCTAssertEqual(url?.port, 8080)
        XCTAssertEqual(url?.path, "/v1/chat/completions")
        XCTAssertEqual(url?.query, "x=1")
    }

    func testRejectsMissingAndNonHTTPEndpoints() {
        XCTAssertNil(LLMEndpoint.chatCompletionsURL(baseURL: " "))
        XCTAssertNil(LLMEndpoint.chatCompletionsURL(baseURL: "ftp://example.com/v1"))
        XCTAssertNil(LLMEndpoint.chatCompletionsURL(baseURL: "not a url"))
    }

    func testParsesStringContent() throws {
        let json = #"{"choices":[{"message":{"role":"assistant","content":"  The dialog asks for a name.  "}}]}"#
        let text = try LLMResponseParser.parse(data: Data(json.utf8))
        XCTAssertEqual(text, "The dialog asks for a name.")
    }

    func testParsesArrayContent() throws {
        let json = """
        {"choices":[{"message":{"content":[{"type":"text","text":"Line one"},{"type":"text","text":"Line two"}]}}]}
        """
        let text = try LLMResponseParser.parse(data: Data(json.utf8))
        XCTAssertEqual(text, "Line one\nLine two")
    }

    func testThrowsAPIMessage() {
        let json = #"{"error":{"message":"Incorrect API key"}}"#
        XCTAssertThrowsError(try LLMResponseParser.parse(data: Data(json.utf8))) { error in
            XCTAssertEqual(error as? LLMError, .api("Incorrect API key"))
        }
    }

    func testThrowsWhenContentIsEmptyOrMalformed() {
        XCTAssertThrowsError(try LLMResponseParser.parse(data: Data("{\"choices\":[{\"message\":{\"content\":\"  \"}}]}".utf8))) { error in
            XCTAssertEqual(error as? LLMError, .empty)
        }
        XCTAssertThrowsError(try LLMResponseParser.parse(data: Data("not-json".utf8))) { error in
            XCTAssertEqual(error as? LLMError, .malformed)
        }
    }
}
