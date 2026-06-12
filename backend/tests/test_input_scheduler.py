import asyncio

import pytest

from app.services import input_scheduler
from app.services.input_scheduler import InputScheduler, VideoSubmission


class FakeSession:
    def __init__(self):
        self.calls = []

    async def send_audio(self, data):
        self.calls.append(("audio", data))

    async def send_video_frame(self, data):
        self.calls.append(("video", data))

    async def send_text(self, data):
        self.calls.append(("text", data))


class ContinuingTextSession(FakeSession):
    def __init__(self, scheduler):
        super().__init__()
        self.scheduler = scheduler
        self.audio_sent = asyncio.Event()
        self.video_sent = asyncio.Event()
        self.next_text = 0

    async def send_audio(self, data):
        await super().send_audio(data)
        self.audio_sent.set()

    async def send_video_frame(self, data):
        await super().send_video_frame(data)
        self.video_sent.set()

    async def send_text(self, data):
        await super().send_text(data)
        self.next_text += 1
        await self.scheduler.submit_text(f"continuing-{self.next_text}")
        await asyncio.sleep(0)


class ContinuingAudioSession(FakeSession):
    def __init__(self, scheduler):
        super().__init__()
        self.scheduler = scheduler
        self.video_sent = asyncio.Event()
        self.next_audio = 0

    async def send_audio(self, data):
        await super().send_audio(data)
        self.next_audio += 1
        await self.scheduler.submit_audio(f"continuing-{self.next_audio}".encode())
        await asyncio.sleep(0)

    async def send_video_frame(self, data):
        await super().send_video_frame(data)
        self.video_sent.set()


def test_audio_queue_capacity_must_be_positive():
    with pytest.raises(ValueError, match="audio_capacity"):
        InputScheduler(audio_capacity=0)


def test_text_queue_capacity_must_be_positive():
    with pytest.raises(ValueError, match="text_capacity"):
        InputScheduler(audio_capacity=4, text_capacity=0)


def test_latest_video_frame_replaces_older_pending_frame():
    scheduler = InputScheduler(audio_capacity=4)

    accepted = scheduler.submit_video(b"old", sequence=1)
    replaced = scheduler.submit_video(b"new", sequence=2)

    assert accepted is VideoSubmission.ACCEPTED
    assert replaced is VideoSubmission.REPLACED
    assert scheduler.take_latest_video() == (b"new", 2)
    assert scheduler.take_latest_video() is None


def test_older_video_frame_cannot_replace_newer_pending_frame():
    scheduler = InputScheduler(audio_capacity=4)

    scheduler.submit_video(b"new", sequence=2)
    rejected = scheduler.submit_video(b"old", sequence=1)

    assert rejected is VideoSubmission.REJECTED
    assert scheduler.take_latest_video() == (b"new", 2)


def test_older_video_frame_is_rejected_after_newer_frame_is_consumed():
    scheduler = InputScheduler(audio_capacity=4)

    scheduler.submit_video(b"new", sequence=10)
    assert scheduler.take_latest_video() == (b"new", 10)

    scheduler.submit_video(b"old", sequence=9)

    assert scheduler.take_latest_video() is None


def test_text_and_audio_are_sent_before_pending_video():
    async def scenario():
        scheduler = InputScheduler(audio_capacity=4)
        session = FakeSession()
        scheduler.submit_video(b"frame", sequence=1)
        await scheduler.submit_audio(b"audio")
        await scheduler.submit_text("text")

        worker = asyncio.create_task(scheduler.run(session))
        await scheduler.close()
        await asyncio.wait_for(worker, timeout=1)

        assert session.calls == [
            ("text", "text"),
            ("audio", b"audio"),
            ("video", b"frame"),
        ]

    asyncio.run(scenario())


def test_audio_queue_applies_backpressure():
    async def scenario():
        scheduler = InputScheduler(audio_capacity=1)
        await scheduler.submit_audio(b"first")
        second = asyncio.create_task(scheduler.submit_audio(b"second"))

        await asyncio.sleep(0)
        assert not second.done()

        assert await scheduler.take_audio() == b"first"
        await asyncio.wait_for(second, timeout=1)
        assert await scheduler.take_audio() == b"second"

    asyncio.run(scenario())


def test_text_queue_applies_backpressure():
    async def scenario():
        scheduler = InputScheduler(audio_capacity=4, text_capacity=1)
        first_send_started = asyncio.Event()
        release_first_send = asyncio.Event()

        class BlockingSession(FakeSession):
            async def send_text(self, data):
                await super().send_text(data)
                if data == "first":
                    first_send_started.set()
                    await release_first_send.wait()

        await scheduler.submit_text("first")
        second_submitted = asyncio.Event()

        async def submit_second():
            await scheduler.submit_text("second")
            second_submitted.set()

        second = asyncio.create_task(submit_second())
        await asyncio.sleep(0)
        assert not second_submitted.is_set()

        worker = asyncio.create_task(scheduler.run(BlockingSession()))
        await asyncio.wait_for(first_send_started.wait(), timeout=1)
        await asyncio.wait_for(second_submitted.wait(), timeout=1)

        release_first_send.set()
        await scheduler.close()
        await asyncio.wait_for(worker, timeout=1)
        await second

    asyncio.run(scenario())


def test_audio_and_video_progress_under_continuing_text_producer():
    async def scenario():
        scheduler = InputScheduler(audio_capacity=4, text_capacity=8)
        session = ContinuingTextSession(scheduler)
        await scheduler.submit_text("first")
        await scheduler.submit_audio(b"audio")
        scheduler.submit_video(b"video", sequence=1)

        worker = asyncio.create_task(scheduler.run(session))
        try:
            await asyncio.wait_for(
                asyncio.gather(
                    session.audio_sent.wait(),
                    session.video_sent.wait(),
                ),
                timeout=1,
            )
            assert session.calls[:3] == [
                ("text", "first"),
                ("audio", b"audio"),
                ("video", b"video"),
            ]
        finally:
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)

    asyncio.run(scenario())


def test_video_progresses_under_continuing_audio_producer():
    async def scenario():
        scheduler = InputScheduler(audio_capacity=16, text_capacity=8)
        session = ContinuingAudioSession(scheduler)
        await scheduler.submit_audio(b"first")
        scheduler.submit_video(b"video", sequence=1)

        worker = asyncio.create_task(scheduler.run(session))
        try:
            await asyncio.wait_for(session.video_sent.wait(), timeout=1)
            assert session.calls[:8] == [
                ("audio", b"first"),
                *[
                    ("audio", f"continuing-{index}".encode())
                    for index in range(1, 8)
                ],
            ]
            assert session.calls[8] == ("video", b"video")
        finally:
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)

    asyncio.run(scenario())


def test_submissions_are_rejected_after_close():
    async def scenario():
        scheduler = InputScheduler(audio_capacity=4, text_capacity=8)
        await scheduler.close()

        with pytest.raises(input_scheduler.SchedulerClosed):
            await scheduler.submit_audio(b"audio")
        with pytest.raises(input_scheduler.SchedulerClosed):
            await scheduler.submit_text("text")
        with pytest.raises(input_scheduler.SchedulerClosed):
            scheduler.submit_video(b"video", sequence=1)

    asyncio.run(scenario())


def test_blocked_audio_submission_loses_to_close_and_is_not_queued():
    async def scenario():
        scheduler = InputScheduler(audio_capacity=1)
        await scheduler.submit_audio(b"first")
        blocked_submit = asyncio.create_task(
            scheduler.submit_audio(b"second")
        )
        await asyncio.sleep(0)
        assert not blocked_submit.done()

        assert await scheduler.take_audio() == b"first"
        await scheduler.close()

        with pytest.raises(input_scheduler.SchedulerClosed):
            await blocked_submit

        session = FakeSession()
        await scheduler.run(session)
        assert session.calls == []

    asyncio.run(scenario())


def test_blocked_text_submission_loses_to_close_and_is_not_queued():
    async def scenario():
        scheduler = InputScheduler(audio_capacity=1, text_capacity=1)
        await scheduler.submit_text("first")
        blocked_submit = asyncio.create_task(
            scheduler.submit_text("second")
        )
        await asyncio.sleep(0)
        assert not blocked_submit.done()

        await scheduler.close()

        with pytest.raises(input_scheduler.SchedulerClosed):
            await blocked_submit

        session = FakeSession()
        await scheduler.run(session)
        assert session.calls == [("text", "first")]

    asyncio.run(scenario())


def test_close_drains_queued_work_and_worker_exits():
    async def scenario():
        scheduler = InputScheduler(audio_capacity=4)
        session = FakeSession()
        await scheduler.submit_text("first")
        await scheduler.submit_text("second")
        await scheduler.submit_audio(b"one")
        await scheduler.submit_audio(b"two")
        scheduler.submit_video(b"frame", sequence=1)

        worker = asyncio.create_task(scheduler.run(session))
        await scheduler.close()
        await asyncio.wait_for(worker, timeout=1)

        assert session.calls == [
            ("text", "first"),
            ("audio", b"one"),
            ("audio", b"two"),
            ("video", b"frame"),
            ("text", "second"),
        ]

    asyncio.run(scenario())


def test_worker_wakes_for_work_submitted_after_it_starts_waiting():
    async def scenario():
        scheduler = InputScheduler(audio_capacity=4)
        session = FakeSession()
        worker = asyncio.create_task(scheduler.run(session))
        await asyncio.sleep(0)

        await scheduler.submit_audio(b"audio")
        await asyncio.sleep(0)
        await scheduler.close()
        await asyncio.wait_for(worker, timeout=1)

        assert session.calls == [("audio", b"audio")]

    asyncio.run(scenario())
