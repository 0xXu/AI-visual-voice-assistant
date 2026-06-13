import base64
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from google import genai
from google.genai import types

from app.core.config import Settings, settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是 SightLine，一名实时 AI 视觉对话助手。你通过用户设备的摄像头和麦克风理解当前环境，并以自然语音提供及时、可靠的帮助。

回答原则：
1. 优先回答用户当前的问题，不要在每次回复时机械地复述整个画面。
2. 只描述当前画面或对话中有依据的信息。看不清、被遮挡、画面过暗或证据不足时，明确说“我无法确认”，并建议用户调整镜头或靠近目标。
3. 清楚区分亲眼可见的事实与合理推测。不要把推测表达成确定事实。
4. 默认使用简短、自然、适合语音收听的句子；先给结论，再补充最有用的细节。用户要求详细说明时再展开。
5. 跟随用户使用的语言进行回答；无法判断时默认使用简体中文。

视觉任务：
- 用户询问环境、物体、位置、颜色、动作或空间关系时，给出具体且可执行的描述。
- 用户要求读字时，按画面中可辨认的顺序准确朗读；不清楚的文字要说明，不要自行补全。
- 发现台阶、车辆、明火、尖锐物、临近障碍等即时危险时，先用一句短句主动警告，再说明方向和距离；无法可靠判断距离时不要编造数值。
- 处理导航或过马路等高风险场景时，只提供辅助观察，明确提醒用户结合现实环境、无障碍设施或可信人员确认。

隐私与安全：
- 不要猜测人物身份，也不要根据外表推断种族、宗教、健康状况、性取向等敏感属性。
- 可以描述明显可见的外观、衣着、姿态和动作，但不要进行贬损性评价。
- 医疗、药物、法律、财务等高风险问题只提供一般信息，并提醒用户向专业人士确认。
- 如果摄像头画面与用户描述冲突，以谨慎方式指出差异，不要假装看到了不存在的内容。

对话方式：
- 语气友好、冷静、直接，不夸张，不使用冗长开场白。
- 用户打断时立即停止当前回答并处理新问题。
- 需要更多视觉信息时，只提出一个最关键的澄清或镜头调整建议。"""


@dataclass(frozen=True, slots=True)
class GeminiResponse:
    payload: dict[str, Any] | None = None
    usage_metadata: types.UsageMetadata | None = None
    model_output: bool = False
    resumption_handle: str | None = None
    resumable: bool | None = None
    go_away: bool = False


def build_live_config(
    app_settings: Settings,
    resume_handle: str | None = None,
) -> types.LiveConnectConfig:
    return types.LiveConnectConfig(
        response_modalities=[types.Modality.AUDIO],
        media_resolution=types.MediaResolution.MEDIA_RESOLUTION_LOW,
        system_instruction=SYSTEM_PROMPT,
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                    voice_name=app_settings.voice_name
                )
            )
        ),
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        realtime_input_config=types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(
                disabled=False,
                prefix_padding_ms=200,
                silence_duration_ms=800,
            )
        ),
        context_window_compression=types.ContextWindowCompressionConfig(
            sliding_window=types.SlidingWindow()
        ),
        session_resumption=types.SessionResumptionConfig(
            handle=resume_handle,
        ),
    )


def _duration_to_milliseconds(duration: str | None) -> int:
    if not duration or not duration.endswith("s"):
        return 0
    try:
        return max(0, int(Decimal(duration[:-1]) * 1_000))
    except InvalidOperation:
        return 0


class GeminiLiveService:
    def __init__(self, app_settings: Settings = settings):
        app_settings.validate_authentication()
        self.settings = app_settings
        self.model = app_settings.model_name

    def _create_client(self) -> genai.Client:
        return genai.Client(
            api_key=self.settings.gemini_api_key.get_secret_value()
        )

    @asynccontextmanager
    async def connect(
        self,
        resume_handle: str | None = None,
    ) -> AsyncIterator["GeminiSession"]:
        client = self._create_client()
        config = build_live_config(self.settings, resume_handle)

        try:
            async with client.aio.live.connect(
                model=self.model,
                config=config,
            ) as session:
                yield GeminiSession(session)
        finally:
            await client.aio.aclose()


class GeminiSession:
    def __init__(self, session: Any):
        self.session = session

    async def send_audio(self, audio_bytes: bytes) -> None:
        await self.session.send_realtime_input(
            audio=types.Blob(
                data=audio_bytes,
                mime_type="audio/pcm;rate=16000",
            )
        )

    async def send_video_frame(self, frame_bytes: bytes) -> None:
        await self.session.send_realtime_input(
            video=types.Blob(data=frame_bytes, mime_type="image/jpeg")
        )

    async def send_text(self, text: str) -> None:
        await self.session.send_realtime_input(text=text)

    async def receive(self) -> AsyncIterator[GeminiResponse]:
        try:
            while True:
                async for response in self.session.receive():
                    resumption_update = response.session_resumption_update
                    if resumption_update is not None:
                        resumable = resumption_update.resumable is True
                        handle = None
                        if resumable and resumption_update.new_handle:
                            handle = resumption_update.new_handle
                        yield GeminiResponse(
                            payload={
                                "type": "session_resumption",
                                "data": {"resumable": resumable},
                            },
                            resumption_handle=handle,
                            resumable=resumable,
                        )

                    server_content = getattr(response, "server_content", None)
                    if server_content and server_content.interrupted:
                        yield GeminiResponse(
                            payload={"type": "interrupted", "data": ""}
                        )

                    usage_metadata = response.usage_metadata
                    if usage_metadata is not None:
                        yield GeminiResponse(usage_metadata=usage_metadata)

                    if server_content:
                        input_transcription = getattr(
                            server_content,
                            "input_transcription",
                            None,
                        )
                        if input_transcription and input_transcription.text:
                            yield GeminiResponse(
                                payload={
                                    "type": "user_text",
                                    "data": input_transcription.text,
                                }
                            )

                        output_transcription = getattr(
                            server_content,
                            "output_transcription",
                            None,
                        )
                        if (
                            output_transcription
                            and output_transcription.text
                        ):
                            yield GeminiResponse(
                                payload={
                                    "type": "text",
                                    "data": output_transcription.text,
                                },
                                model_output=True,
                            )

                        model_turn = getattr(
                            server_content, "model_turn", None
                        )
                        if model_turn:
                            for part in model_turn.parts:
                                inline_data = getattr(
                                    part, "inline_data", None
                                )
                                if inline_data and inline_data.data:
                                    yield GeminiResponse(
                                        payload={
                                            "type": "audio",
                                            "data": base64.b64encode(
                                                inline_data.data
                                            ).decode("ascii"),
                                        },
                                        model_output=True,
                                    )

                        if getattr(
                            server_content, "turn_complete", False
                        ):
                            logger.debug("Gemini 本轮回复已完成")
                            yield GeminiResponse(
                                payload={
                                    "type": "turn_complete",
                                    "data": "",
                                }
                            )

                    go_away = response.go_away
                    if go_away is not None:
                        yield GeminiResponse(
                            payload={
                                "type": "go_away",
                                "data": {
                                    "time_left_ms": (
                                        _duration_to_milliseconds(
                                            go_away.time_left
                                        )
                                    )
                                },
                            },
                            go_away=True,
                        )
        except Exception:
            logger.exception("接收 Gemini 实时响应时发生异常")
            raise
