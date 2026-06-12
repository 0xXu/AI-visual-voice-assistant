import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress
from enum import Enum

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from app.api.messages import ClientMessageError, parse_client_message
from app.core.config import ConfigurationError, settings
from app.services.gemini_service import GeminiLiveService, GeminiSession
from app.services.input_scheduler import InputScheduler, VideoSubmission
from app.services.session_runtime import (
    SessionIdleTimeout,
    SessionLifetimeExceeded,
    SessionRuntime,
)
from app.services.usage import SessionUsage

logger = logging.getLogger(__name__)
router = APIRouter()

_AUDIO_BACKPRESSURE_ERROR = "音频输入处理繁忙，请稍后重试"
_TEXT_BACKPRESSURE_ERROR = "文本输入处理繁忙，请稍后重试"


class SessionEndReason(Enum):
    STOPPED = "stopped"
    SESSION_ENDED = "session_ended"
    BUDGET_EXCEEDED = "budget_exceeded"


def _observe_task_result(task: asyncio.Task[object]) -> None:
    try:
        exception = task.exception()
    except asyncio.CancelledError:
        return
    if exception is not None:
        logger.error(
            "后台任务延迟结束并发生异常：%s",
            exception,
            exc_info=(
                type(exception),
                exception,
                exception.__traceback__,
            ),
        )


async def _cancel_tasks_with_timeout(
    tasks: set[asyncio.Task[object]],
    timeout: float,
) -> None:
    for task in tasks:
        if not task.done():
            task.cancel()

    done, pending = await asyncio.wait(tasks, timeout=timeout)
    for task in done:
        _observe_task_result(task)
    for task in pending:
        task.add_done_callback(_observe_task_result)
    if pending:
        logger.warning(
            "取消后台任务超过硬超时，转为异步观察：%s",
            ", ".join(sorted(task.get_name() for task in pending)),
        )


async def _send_error(websocket: WebSocket, message: str) -> None:
    if websocket.client_state == WebSocketState.CONNECTED:
        await websocket.send_json({"type": "error", "data": message})


async def _forward_gemini_responses(
    websocket: WebSocket,
    session: GeminiSession,
    usage: SessionUsage,
) -> SessionEndReason:
    async for response in session.receive():
        if response.usage_metadata is not None:
            usage.record_gemini_usage(response.usage_metadata)
            if usage.budget_exceeded:
                logger.info(
                    "会话 token 预算已用尽：%s/%s",
                    usage.total_tokens,
                    usage.token_budget,
                )
                return SessionEndReason.BUDGET_EXCEEDED
        if response.payload is not None:
            if response.model_output:
                usage.record_response()
            await websocket.send_json(response.payload)
    return SessionEndReason.SESSION_ENDED


async def _record_activity_after(
    submission: Awaitable[None],
    runtime: SessionRuntime | None,
    record_usage: Callable[[], None] | None = None,
) -> None:
    await submission
    if record_usage is not None:
        record_usage()
    if runtime is not None:
        runtime.record_activity()


async def _forward_client_messages(
    websocket: WebSocket,
    scheduler: InputScheduler,
    runtime: SessionRuntime | None = None,
    usage: SessionUsage | None = None,
) -> SessionEndReason:
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
            elif message.type == "start_session":
                continue
            elif message.type == "stop_session":
                return SessionEndReason.STOPPED
            elif message.type == "audio":
                assert isinstance(message.data, bytes)
                if pending_audio is not None:
                    await _send_error(
                        websocket,
                        _AUDIO_BACKPRESSURE_ERROR,
                    )
                    continue
                record_audio = None
                if usage is not None:
                    record_audio = (
                        lambda data=message.data: usage.record_audio(data)
                    )
                pending_audio = asyncio.create_task(
                    _record_activity_after(
                        scheduler.submit_audio(message.data),
                        runtime,
                        record_audio,
                    ),
                    name="提交音频输入",
                )
                await asyncio.sleep(0)
            elif message.type == "video_frame":
                assert isinstance(message.data, bytes)
                assert message.sequence is not None
                submission = scheduler.submit_video(
                    message.data,
                    message.sequence,
                )
                if (
                    usage is not None
                    and submission is not VideoSubmission.REJECTED
                ):
                    usage.record_video(
                        message.data,
                        replaced=submission is VideoSubmission.REPLACED,
                    )
                if (
                    runtime is not None
                    and submission is not VideoSubmission.REJECTED
                ):
                    runtime.record_activity()
            elif message.type == "text":
                assert isinstance(message.data, str)
                if pending_text is not None:
                    await _send_error(
                        websocket,
                        _TEXT_BACKPRESSURE_ERROR,
                    )
                    continue
                record_text = None
                if usage is not None:
                    record_text = (
                        lambda data=message.data: usage.record_text(data)
                    )
                pending_text = asyncio.create_task(
                    _record_activity_after(
                        scheduler.submit_text(message.data),
                        runtime,
                        record_text,
                    ),
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


async def _wait_for_start(websocket: WebSocket) -> None:
    while True:
        raw_message = await websocket.receive_text()
        try:
            message = parse_client_message(raw_message, settings)
        except ClientMessageError as exc:
            logger.warning("收到无效客户端消息：%s", exc)
            await _send_error(websocket, str(exc))
            continue

        if message.type == "start_session":
            return
        if message.type == "ping":
            await websocket.send_json({"type": "pong", "data": ""})
            continue
        if message.type == "pong":
            continue
        await _send_error(websocket, "请先发送 start_session")


def _create_runtime() -> SessionRuntime:
    return SessionRuntime(
        idle_seconds=settings.session_idle_seconds,
        max_seconds=settings.session_max_seconds,
    )


def _create_usage() -> SessionUsage:
    return SessionUsage(token_budget=settings.session_token_budget)


async def _run_session(
    websocket: WebSocket,
    session: GeminiSession,
    runtime: SessionRuntime | None = None,
    usage: SessionUsage | None = None,
) -> SessionEndReason:
    if runtime is None:
        runtime = _create_runtime()
    if usage is None:
        usage = _create_usage()

    scheduler = InputScheduler(
        audio_capacity=settings.audio_queue_capacity,
        text_capacity=settings.text_queue_capacity,
    )
    scheduler_task = asyncio.create_task(
        scheduler.run(session),
        name="发送模型输入",
    )
    client_task = asyncio.create_task(
        _forward_client_messages(websocket, scheduler, runtime, usage),
        name="接收客户端消息",
    )
    response_task = asyncio.create_task(
        _forward_gemini_responses(websocket, session, usage),
        name="转发模型响应",
    )
    tasks = {
        client_task,
        scheduler_task,
        response_task,
        asyncio.create_task(
            _keepalive(websocket),
            name="连接保活",
        ),
        asyncio.create_task(
            runtime.wait_until_expired(),
            name="监控会话期限",
        ),
    }
    end_reason = SessionEndReason.SESSION_ENDED

    try:
        done, _ = await asyncio.wait(
            tasks,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if client_task in done:
            end_reason = client_task.result()
        for task in done:
            if task is client_task:
                continue
            exception = task.exception()
            if exception:
                if (
                    end_reason is SessionEndReason.STOPPED
                    and isinstance(
                        exception,
                        (SessionIdleTimeout, SessionLifetimeExceeded),
                    )
                ):
                    continue
                raise exception
        if (
            response_task in done
            and end_reason is not SessionEndReason.STOPPED
        ):
            end_reason = response_task.result()
    finally:
        scheduler_exception: BaseException | None = None
        if end_reason is SessionEndReason.BUDGET_EXCEEDED:
            scheduler_task.cancel()
            await scheduler.close()
            await _cancel_tasks_with_timeout(
                tasks,
                settings.scheduler_shutdown_timeout_seconds,
            )
        else:
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
                await _cancel_tasks_with_timeout(
                    tasks,
                    settings.scheduler_shutdown_timeout_seconds,
                )
            if (
                scheduler_exception is None
                and scheduler_task.done()
                and not scheduler_task.cancelled()
            ):
                scheduler_exception = scheduler_task.exception()
            if scheduler_exception is not None:
                raise scheduler_exception
    return end_reason


async def _serve_websocket(
    websocket: WebSocket,
    *,
    service_factory: Callable[[], GeminiLiveService] = GeminiLiveService,
    runtime_factory: Callable[[], SessionRuntime] = _create_runtime,
    usage_factory: Callable[[], SessionUsage] = _create_usage,
) -> None:
    await websocket.accept()
    logger.info("客户端已连接")

    try:
        while True:
            await _wait_for_start(websocket)
            try:
                service = service_factory()
                terminal_status = "stopped"
                usage: SessionUsage | None = None
                async with service.connect() as session:
                    usage = usage_factory()
                    await websocket.send_json({
                        "type": "status",
                        "data": "connected",
                    })
                    logger.info(
                        "Gemini Live 会话已建立，模型：%s",
                        service.model,
                    )
                    try:
                        reason = await _run_session(
                            websocket,
                            session,
                            runtime_factory(),
                            usage,
                        )
                    except SessionIdleTimeout:
                        terminal_status = "idle_timeout"
                    except SessionLifetimeExceeded:
                        terminal_status = "max_duration"
                    else:
                        if reason is SessionEndReason.BUDGET_EXCEEDED:
                            terminal_status = "budget_exceeded"
                assert usage is not None
                await websocket.send_json({
                    "type": "status",
                    "data": terminal_status,
                })
                await websocket.send_json({
                    "type": "usage",
                    "data": usage.to_dict(),
                })
                logger.info(
                    "云会话已结束，状态：%s，token：%s",
                    terminal_status,
                    usage.total_tokens,
                )
            except ConfigurationError as exc:
                logger.error("Gemini 配置错误：%s", exc)
                await _send_error(
                    websocket,
                    "服务配置不完整，请联系管理员",
                )
            except WebSocketDisconnect:
                raise
            except Exception:
                logger.exception("实时会话发生异常")
                await _send_error(
                    websocket,
                    "实时会话发生异常，请稍后重试",
                )
    except WebSocketDisconnect:
        logger.info("客户端已断开连接")
    finally:
        if websocket.client_state == WebSocketState.CONNECTED:
            with suppress(Exception):
                await websocket.close()
        logger.info("实时会话已结束")


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await _serve_websocket(websocket)
