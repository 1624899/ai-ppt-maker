from __future__ import annotations

import json
import unittest

from ppt_system.integrations.chat_response_parser import extract_chat_completion_text
from ppt_system.integrations.chat_stream_parser import parse_chat_completion_sse


class ChatStreamParserTests(unittest.TestCase):
    def test_merges_chat_completion_chunks_with_crlf_comments_and_done_marker(self) -> None:
        chunks = [
            {
                "id": "chatcmpl_test",
                "object": "chat.completion.chunk",
                "created": 1782267521,
                "model": "gpt-5.5",
                "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
            },
            {
                "id": "chatcmpl_test",
                "object": "chat.completion.chunk",
                "created": 1782267521,
                "model": "gpt-5.5",
                "choices": [{"index": 0, "delta": {"content": '{"title":"提问'}, "finish_reason": None}],
            },
            {
                "id": "chatcmpl_test",
                "object": "chat.completion.chunk",
                "created": 1782267521,
                "model": "gpt-5.5",
                "choices": [{"index": 0, "delta": {"content": '即竞争力"}'}, "finish_reason": "stop"}],
            },
        ]
        sse_text = ": keep-alive\r\n\r\n" + "\r\n\r\n".join(
            f"event: completion\r\ndata: {json.dumps(chunk, ensure_ascii=False)}" for chunk in chunks
        )
        sse_text = f"{sse_text}\r\n\r\ndata: [DONE]\r\n\r\n"

        body = parse_chat_completion_sse(sse_text)

        self.assertEqual(extract_chat_completion_text(body), '{"title":"提问即竞争力"}')

    def test_merges_response_api_output_text_deltas(self) -> None:
        events = [
            {"type": "response.output_text.delta", "delta": '{"title":"提问'},
            {"type": "response.output_text.delta", "delta": '即竞争力"}'},
            {"type": "response.completed", "response": {"id": "resp_test"}},
        ]
        sse_text = "\n\n".join(f"data: {json.dumps(event, ensure_ascii=False)}" for event in events)

        body = parse_chat_completion_sse(sse_text)

        self.assertEqual(body["output_text"], '{"title":"提问即竞争力"}')


if __name__ == "__main__":
    unittest.main()
