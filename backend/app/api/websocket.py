import asyncio
import logging
from contextlib import suppress

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from app.api.messages import ClientMessageError, parse_client_message
from app.core.config import ConfigurationError, settings
from app.services.gemini_service import GeminiLiveService, GeminiSession
from app.services.input_scheduler import InputScheduler

logger = logging.getLogger(__name__)
router = APIRouter()

_AUDIO_BACKPRESSURE_ERROR = "音频输入处理繁忙，请稍后重试"
_TEXT_BACKPRESSURE_ERROR = "文本输入处理繁忙，请稍后重试"


async def _send_error(websocket: WebSocket, message: str) -> None:
    if websocket.client_state == WebSocketState.CONNECTED:
        await websocket.send_json({"type": "error", "data": message})


async def _forward_gemini_responses(
    websocket: WebSocket,
    session: GeminiSession,
) -> None:
    async for response in session.receive():
        await websocket.send_json(response)


async def _forward_client_messages(
    websocket: WebSocket,
    scheduler: InputScheduler,
) -> None:
    pending_audio: asyncio.Task[None] | None = None
    pending_text: asyncio.Task[None] | None = None

    try:
        while True:
            if pending_audio is not None and pending_audio.done():
                pending_audio.result()
                pending_audio = None
            if pending_text is not None and pending_text.done():
                pending_text.result()
                pending_text = None

            raw_message = await websocket.receive_text()
            try:
                message = parse_client_message(raw_message, settings)
            except ClientMessageError as exc:
                logger.warning("收到无效客户端消息：%s", exc)
                await _send_error(websocket, str(exc))
                continue

            if message.type == "ping":
                await websocket.send_json({"type": "pong", "data": ""})
            elif message.type == "pong":
                continue
            elif message.type == "audio":
                assert isinstance(message.data, bytes)
                if pending_audio is not None:
                    await _send_error(
                        websocket,
                        _AUDIO_BACKPRESSURE_ERROR,
                    )
                    continue
                pending_audio = asyncio.create_task(
                    scheduler.submit_audio(message.data),
                    name="提交音频输入",
                )
                await asyncio.sleep(0)
            elif message.type == "video_frame":
                assert isinstance(message.data, bytes)
                assert message.sequence is not None
                scheduler.submit_video(message.data, message.sequence)
            elif message.type == "text":
                assert isinstance(message.data, str)
                if pending_text is not None:
                    await _send_error(
                        websocket,
                        _TEXT_BACKPRESSURE_ERROR,
                    )
                    continue
                pending_text = asyncio.create_task(
                    scheduler.submit_text(message.data),
                    name="提交文本输入",
                )
                await asyncio.sleep(0)
    finally:
        pending = [
            task
            for task in (pending_audio, pending_text)
            if task is not None
        ]
        for task in pending:
            if not task.done():
                task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)


async def _keepalive(websocket: WebSocket) -> None:
    while True:
        await asyncio.sleep(settings.websocket_keepalive_seconds)
        await websocket.send_json({"type": "ping", "data": ""})


async def _run_session(
    websocket: WebSocket,
    session: GeminiSession,
) -> None:
    scheduler = InputScheduler(
        audio_capacity=settings.audio_queue_capacity,
        text_capacity=settings.text_queue_capacity,
    )
    scheduler_task = asyncio.create_task(
        scheduler.run(session),
        name="发送模型输入",
    )
    tasks = {
        asyncio.create_task(
            _forward_client_messages(websocket, scheduler),
            name="接收客户端消息",
        ),
        scheduler_task,
        asyncio.create_task(
            _forward_gemini_responses(websocket, session),
            name="转发模型响应",
        ),
        asyncio.create_task(
            _keepalive(websocket),
            name="连接保活",
        ),
    }

    try:
        done, _ = await asyncio.wait(
            tasks,
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in done:
            exception = task.exception()
            if exception:
                raise exception
    finally:
        scheduler_exception: BaseException | None = None
        await scheduler.close()
        try:
            await asyncio.wait_for(
                asyncio.shield(scheduler_task),
                timeout=settings.scheduler_shutdown_timeout_seconds,
            )
        except TimeoutError:
            scheduler_task.cancel()
        except asyncio.CancelledError:
            scheduler_task.cancel()
            raise
        except Exception as exc:
            scheduler_exception = exc
        finally:
            for task in tasks:
                if task is not scheduler_task:
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        if (
            scheduler_exception is None
            and scheduler_task.done()
            and not scheduler_task.cancelled()
        ):
            scheduler_exception = scheduler_task.exception()
        if scheduler_exception is not None:
            raise scheduler_exception


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    logger.info("客户端已连接")

    try:
        service = GeminiLiveService()
        async with service.connect() as session:
            await websocket.send_json({
                "type": "status",
                "data": "connected",
            })
            logger.info("Gemini Live 会话已建立，模型：%s", service.model)
            await _run_session(websocket, session)
    except WebSocketDisconnect:
        logger.info("客户端已断开连接")
    except ConfigurationError as exc:
        logger.error("Gemini 配置错误：%s", exc)
        await _send_error(websocket, "服务配置不完整，请联系管理员")
    except Exception:
        logger.exception("实时会话发生异常")
        with suppress(Exception):
            await _send_error(websocket, "实时会话发生异常，请稍后重试")
    finally:
        if websocket.client_state == WebSocketState.CONNECTED:
            with suppress(Exception):
                await websocket.close()
        logger.info("实时会话已结束")
