import json
import unittest

import httpx

from translator.config import ANTHROPIC_BASE_URL
from translator.llm import (
    AnthropicMessagesLLMClient,
    OpenAICompatibleLLMClient,
    _extract_translation_map,
    _parse_json_from_text,
)
from translator.pipeline import is_retryable_run_error


def _anthropic_text_response(text: str) -> dict:
    return {"content": [{"type": "text", "text": text}]}


class TranslationPayloadTests(unittest.TestCase):
    def test_parse_json_from_text_tolerates_trailing_garbage_after_object(self):
        payload = _parse_json_from_text('{"ok": true} trailing noise')

        self.assertEqual(payload, {"ok": True})

    def test_extract_translation_map_supports_keyed_object(self):
        payload = {"translations": {"seg_0001": "第一句", "seg_0002": "第二句"}}

        translation_map = _extract_translation_map(payload)

        self.assertEqual(translation_map["seg_0001"], "第一句")
        self.assertEqual(translation_map["seg_0002"], "第二句")

    def test_translate_repairs_missing_segments_with_followup_request(self):
        client = OpenAICompatibleLLMClient(
            api_key="test-key",
            base_url="https://example.com/v1",
            model="demo-model",
        )
        responses = iter(
            [
                {"translations": {"seg_0001": "第一句"}},
                {"translations": {"seg_0002": "第二句"}},
            ]
        )
        requested_tool_names = []

        def fake_call_json(
            system_prompt,
            user_prompt,
            model,
            temperature,
            max_tokens=None,
            schema=None,
            tool_name="return_json",
            tool_description="",
        ):
            requested_tool_names.append(tool_name)
            return next(responses)

        client._call_json = fake_call_json  # type: ignore[method-assign]

        result = client.translate(
            book_metadata={"title": "Demo", "author": "Tester", "identifier": "demo", "language": "ja"},
            story_state={},
            segments=[
                {"id": "seg_0001", "text": "太郎は学校へ行った。"},
                {"id": "seg_0002", "text": "花子に会った。"},
            ],
            source_language="日语",
            target_language="中文",
        )

        self.assertEqual(
            result,
            {
                "seg_0001": "第一句",
                "seg_0002": "第二句",
            },
        )
        self.assertEqual(requested_tool_names, ["return_translations", "return_translations"])

class AnthropicMessagesClientTests(unittest.TestCase):
    def test_endpoint_normalization(self):
        resolve = AnthropicMessagesLLMClient.resolve_messages_endpoint
        self.assertEqual(resolve(None), f"{ANTHROPIC_BASE_URL}/v1/messages")
        self.assertEqual(resolve("https://gateway.example.com"), "https://gateway.example.com/v1/messages")
        self.assertEqual(resolve("https://gateway.example.com/"), "https://gateway.example.com/v1/messages")
        self.assertEqual(resolve("https://gateway.example.com/v1"), "https://gateway.example.com/v1/messages")
        self.assertEqual(
            resolve("https://gateway.example.com/api/v1/messages"),
            "https://gateway.example.com/api/v1/messages",
        )

    def _make_client(self, handler) -> AnthropicMessagesLLMClient:
        return AnthropicMessagesLLMClient(
            api_key="sk-ant-test",
            base_url="https://gateway.example.com",
            model="claude-test",
            http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    def test_summarize_posts_to_messages_endpoint_and_validates_payload(self):
        seen_requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen_requests.append(request)
            body = json.loads(request.content.decode("utf-8"))
            self.assertEqual(body["model"], "claude-test")
            self.assertEqual(body["max_tokens"], 2048)
            self.assertIn("待分析片段", body["messages"][0]["content"])
            payload = {
                "chapter_summary": "摘要",
                "characters": [{"name": "太郎", "description": "学生", "aliases": ["タロウ"]}],
                "glossary": [{"source": "東京", "target": "东京", "note": ""}],
            }
            return httpx.Response(200, json=_anthropic_text_response(json.dumps(payload, ensure_ascii=False)))

        client = self._make_client(handler)
        result = client.summarize(
            book_metadata={"title": "Demo"},
            story_state={},
            segments=[{"id": "seg_0001", "text": "太郎は学校へ行った。"}],
            source_language="日语",
            target_language="中文",
        )

        self.assertEqual(len(seen_requests), 1)
        request = seen_requests[0]
        self.assertEqual(request.url.host, "gateway.example.com")
        self.assertEqual(request.url.path, "/v1/messages")
        self.assertEqual(request.headers["x-api-key"], "sk-ant-test")
        self.assertEqual(request.headers["anthropic-version"], "2023-06-01")
        self.assertEqual(result["chapter_summary"], "摘要")
        self.assertEqual(result["characters"][0]["name"], "太郎")
        self.assertEqual(result["glossary"][0]["target"], "东京")

    def test_translate_repairs_missing_segments_with_followup_request(self):
        responses = iter(
            [
                {"translations": {"seg_0001": "第一句"}},
                {"translations": {"seg_0001": "第一句", "seg_0002": "第二句"}},
            ]
        )
        request_count = []

        def handler(request: httpx.Request) -> httpx.Response:
            request_count.append(request)
            return httpx.Response(200, json=_anthropic_text_response(json.dumps(next(responses), ensure_ascii=False)))

        client = self._make_client(handler)
        result = client.translate(
            book_metadata={"title": "Demo"},
            story_state={},
            segments=[
                {"id": "seg_0001", "text": "一"},
                {"id": "seg_0002", "text": "二"},
            ],
            source_language="日语",
            target_language="中文",
        )

        self.assertEqual(result, {"seg_0001": "第一句", "seg_0002": "第二句"})
        self.assertEqual(len(request_count), 2)

    def test_call_json_repairs_invalid_json_within_retry_budget(self):
        replies = iter(["这不是 json", json.dumps({"ok": 1})])
        bodies = []

        def handler(request: httpx.Request) -> httpx.Response:
            bodies.append(json.loads(request.content.decode("utf-8")))
            return httpx.Response(200, json=_anthropic_text_response(next(replies)))

        client = self._make_client(handler)
        result = client._call_json("system", "user", "claude-test", temperature=0.0)

        self.assertEqual(result, {"ok": 1})
        self.assertEqual(len(bodies), 2)
        self.assertEqual(bodies[1]["messages"][1]["role"], "assistant")
        self.assertEqual(bodies[1]["messages"][2]["role"], "user")
        self.assertIn("合法 json", bodies[1]["messages"][2]["content"])

    def test_rate_limit_response_maps_to_retryable_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, json={"error": {"type": "rate_limit_error", "message": "slow down"}})

        client = self._make_client(handler)
        with self.assertRaises(RuntimeError) as ctx:
            client.summarize(
                book_metadata={},
                story_state={},
                segments=[{"id": "seg_0001", "text": "x"}],
                source_language="日语",
                target_language="中文",
            )

        self.assertIn("rate limit", str(ctx.exception))
        self.assertTrue(is_retryable_run_error(ctx.exception))

    def test_auth_error_is_not_retryable(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": {"type": "authentication_error", "message": "bad key"}})

        client = self._make_client(handler)
        with self.assertRaises(RuntimeError) as ctx:
            client.summarize(
                book_metadata={},
                story_state={},
                segments=[{"id": "seg_0001", "text": "x"}],
                source_language="日语",
                target_language="中文",
            )

        self.assertFalse(is_retryable_run_error(ctx.exception))


if __name__ == "__main__":
    unittest.main()
