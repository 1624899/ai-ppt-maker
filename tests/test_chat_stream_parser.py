from __future__ import annotations

import json
import unittest

from ppt_system.integrations.chat_response_parser import extract_response_text
from ppt_system.integrations.chat_stream_parser import parse_response_sse


class ResponseStreamParserTests(unittest.TestCase):
    def test_merges_response_api_output_text_deltas_with_crlf_comments_and_done_marker(self) -> None:
        events = [
            {"type": "response.created", "response": {"id": "resp_test"}},
            {"type": "response.output_text.delta", "delta": '{"title":"提问'},
            {"type": "response.output_text.delta", "delta": '即竞争力"}'},
            {"type": "response.completed", "response": {"id": "resp_test"}},
        ]
        sse_text = ": keep-alive\r\n\r\n" + "\r\n\r\n".join(
            f"event: response\r\ndata: {json.dumps(event, ensure_ascii=False)}" for event in events
        )
        sse_text = f"{sse_text}\r\n\r\ndata: [DONE]\r\n\r\n"

        body = parse_response_sse(sse_text)

        self.assertEqual(extract_response_text(body), '{"title":"提问即竞争力"}')

    def test_merges_completed_text_events_when_no_deltas_are_sent(self) -> None:
        events = [
            {"type": "response.output_text.done", "text": '{"title":"模型规划"}'},
            {"type": "response.completed", "response": {"id": "resp_test", "status": "completed"}},
        ]
        sse_text = "\n\n".join(f"data: {json.dumps(event, ensure_ascii=False)}" for event in events)

        body = parse_response_sse(sse_text)

        self.assertEqual(extract_response_text(body), '{"title":"模型规划"}')

    def test_merges_completed_output_item_when_no_deltas_are_sent(self) -> None:
        events = [
            {
                "type": "response.output_item.done",
                "item": {
                    "type": "message",
                    "content": [{"type": "output_text", "text": '{"title":"规划完成"}'}],
                },
            },
            {"type": "response.completed", "response": {"id": "resp_test", "status": "completed"}},
        ]
        sse_text = "\n\n".join(f"data: {json.dumps(event, ensure_ascii=False)}" for event in events)

        body = parse_response_sse(sse_text)

        self.assertEqual(extract_response_text(body), '{"title":"规划完成"}')

    def test_does_not_duplicate_text_shared_by_completed_events(self) -> None:
        text = '{"title":"统一完成文本"}'
        events = [
            {"type": "response.output_text.done", "text": text},
            {"type": "response.content_part.done", "part": {"text": text}},
            {
                "type": "response.output_item.done",
                "item": {"content": [{"type": "output_text", "text": text}]},
            },
            {"type": "response.completed", "response": {"id": "resp_test", "status": "completed"}},
        ]
        sse_text = "\n\n".join(f"data: {json.dumps(event, ensure_ascii=False)}" for event in events)

        body = parse_response_sse(sse_text)

        self.assertEqual(extract_response_text(body), text)

    def test_accepts_gateway_event_with_untagged_final_response_output(self) -> None:
        event = {
            "response": {
                "id": "resp_gateway",
                "status": "completed",
                "output": [{
                    "type": "message",
                    "status": "completed",
                    "content": [{"type": "output_text", "text": '{"title":"网关响应"}'}],
                }],
            }
        }
        body = parse_response_sse(f"data: {json.dumps(event, ensure_ascii=False)}\n\n")

        self.assertEqual(extract_response_text(body), '{"title":"网关响应"}')


if __name__ == "__main__":
    unittest.main()
