from google.genai import types

from app.services.usage import SessionUsage


def test_aggregates_accepted_input_tokens_duration_and_latency():
    now = 100.0
    usage = SessionUsage(token_budget=50, clock=lambda: now)

    now = 101.0
    usage.record_audio(b"1234")
    usage.record_text("你好")
    usage.record_video(b"frame", replaced=False)
    usage.record_video(b"new-frame", replaced=True)
    usage.record_gemini_usage(
        types.UsageMetadata(
            prompt_token_count=10,
            response_token_count=4,
            total_token_count=14,
        )
    )
    usage.record_gemini_usage(
        types.UsageMetadata(
            prompt_token_count=3,
            response_token_count=2,
            total_token_count=5,
        )
    )

    now = 101.4
    usage.record_response()
    now = 103.0

    assert usage.to_dict() == {
        "audio_bytes": 4,
        "text_chars": 2,
        "video_frames": 2,
        "video_replaced_frames": 1,
        "video_bytes": 14,
        "input_tokens": 13,
        "output_tokens": 6,
        "total_tokens": 19,
        "duration_ms": 3000,
        "first_response_latency_ms": 400,
    }
    assert usage.budget_exceeded is False


def test_budget_is_exceeded_when_total_tokens_reach_limit():
    usage = SessionUsage(token_budget=10)

    usage.record_gemini_usage(types.UsageMetadata(total_token_count=10))

    assert usage.budget_exceeded is True
