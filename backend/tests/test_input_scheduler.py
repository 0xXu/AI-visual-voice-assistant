import asyncio

import pytest

from app.services.input_scheduler import InputScheduler


class FakeSession:
    def __init__(self):
        self.calls = []

    async def send_audio(self, data):
        self.calls.append(("audio", data))

    async def send_video_frame(self, data):
        self.calls.append(("video", data))

    async def send_text(self, data):
        self.calls.append(("text", data))


def test_audio_queue_capacity_must_be_positive():
    with pytest.raises(ValueError, match="audio_capacity"):
        InputScheduler(audio_capacity=0)


def test_latest_video_frame_replaces_older_pending_frame():
    scheduler = InputScheduler(audio_capacity=4)

    scheduler.submit_video(b"old", sequence=1)
    scheduler.submit_video(b"new", sequence=2)

    assert scheduler.take_latest_video() == (b"new", 2)
    assert scheduler.take_latest_video() is None


def test_older_video_frame_cannot_replace_newer_pending_frame():
    scheduler = InputScheduler(audio_capacity=4)

    scheduler.submit_video(b"new", sequence=2)
    scheduler.submit_video(b"old", sequence=1)

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
            ("text", "second"),
            ("audio", b"one"),
            ("audio", b"two"),
            ("video", b"frame"),
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
