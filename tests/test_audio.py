"""Unit tests for audio.cpp service integration and API endpoints."""

import asyncio
import json
import pytest
import httpx
from fastapi.testclient import TestClient

from core.config import AudioConfig
from logic.audio import (
    AudioService,
    AudioServiceError,
    AudioServiceUnavailableError,
    AudioSynthesisError,
    AudioTranscriptionError,
)
from api.server import app


def test_audio_service_unreachable_raises_unavailable() -> None:
    """Operations raise AudioServiceUnavailableError when server is unreachable."""

    async def run():
        def handler(request: httpx.Request):
            raise httpx.ConnectError("Connection refused")

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        service = AudioService(
            config=AudioConfig(enabled=True, endpoint="http://unreachable:8080"),
            client=client,
        )

        with pytest.raises(AudioServiceUnavailableError):
            await service.list_models()

        with pytest.raises(AudioServiceUnavailableError):
            await service.synthesize("test")

        with pytest.raises(AudioServiceUnavailableError):
            await service.transcribe(b"test")

        with pytest.raises(AudioServiceUnavailableError):
            await service.run_task("model", {})

    asyncio.run(run())


def test_audio_service_disabled_by_default() -> None:
    """Audio service is disabled by default and gracefully rejects operations."""

    async def run():
        config = AudioConfig(enabled=False)
        service = AudioService(config=config)
        assert not service.is_enabled
        assert not await service.check_health()
        assert await service.list_models() == []

        with pytest.raises(AudioServiceError, match="disabled"):
            await service.synthesize("Hello world")

        with pytest.raises(AudioServiceError, match="disabled"):
            await service.transcribe(b"RIFF dummy audio")

        with pytest.raises(AudioServiceError, match="disabled"):
            await service.run_task("model", {})

        await service.close()

    asyncio.run(run())


def test_audio_service_health_check() -> None:
    """Health check tests /health endpoint and falls back to /v1/models."""

    async def run():
        # Case 1: /health succeeds
        def handler_ok(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "ok"})
            return httpx.Response(404)

        transport = httpx.MockTransport(handler_ok)
        client = httpx.AsyncClient(transport=transport)
        service = AudioService(
            config=AudioConfig(enabled=True, endpoint="http://mock-audio:8080"),
            client=client,
        )
        assert await service.check_health() is True

        # Case 2: /health 404, but /v1/models succeeds
        def handler_models(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/v1/models":
                return httpx.Response(200, json={"data": []})
            return httpx.Response(404)

        transport2 = httpx.MockTransport(handler_models)
        client2 = httpx.AsyncClient(transport=transport2)
        service2 = AudioService(
            config=AudioConfig(enabled=True, endpoint="http://mock-audio:8080"),
            client=client2,
        )
        assert await service2.check_health() is True

        # Case 3: Both fail
        def handler_fail(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500)

        transport3 = httpx.MockTransport(handler_fail)
        client3 = httpx.AsyncClient(transport=transport3)
        service3 = AudioService(
            config=AudioConfig(enabled=True, endpoint="http://mock-audio:8080"),
            client=client3,
        )
        assert await service3.check_health() is False

    asyncio.run(run())


def test_audio_service_list_models() -> None:
    """list_models parses OpenAI-style response containing models."""

    async def run():
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/v1/models"
            return httpx.Response(
                200,
                json={"data": [{"id": "pocket-tts"}, {"id": "qwen3-asr"}]},
            )

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        service = AudioService(
            config=AudioConfig(enabled=True, endpoint="http://mock-audio:8080"),
            client=client,
        )
        models = await service.list_models()
        assert models == ["pocket-tts", "qwen3-asr"]

    asyncio.run(run())


def test_audio_service_synthesize() -> None:
    """synthesize constructs valid payload and returns audio bytes."""

    async def run():
        recorded_requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            recorded_requests.append(request)
            assert request.url.path == "/v1/audio/speech"
            body = json.loads(request.content.decode("utf-8"))
            assert body["input"] == "A dark corridor awaits."
            assert body["model"] == "pocket-tts"
            assert body["speed"] == 1.1
            return httpx.Response(
                200, content=b"RIFFWAVEDATA", headers={"Content-Type": "audio/wav"}
            )

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        service = AudioService(
            config=AudioConfig(
                enabled=True,
                endpoint="http://mock-audio:8080",
                tts_model="pocket-tts",
                speaking_rate=1.1,
            ),
            client=client,
        )

        # Empty text raises error
        with pytest.raises(AudioSynthesisError, match="empty text"):
            await service.synthesize("")

        wav_bytes = await service.synthesize("A dark corridor awaits.")
        assert wav_bytes == b"RIFFWAVEDATA"
        assert len(recorded_requests) == 1

    asyncio.run(run())


def test_audio_service_voice_cloning_payload() -> None:
    """synthesize attaches voice cloning reference parameters when enabled."""

    async def run():
        recorded_bodies = []

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content.decode("utf-8"))
            recorded_bodies.append(body)
            return httpx.Response(200, content=b"RIFFWAVE")

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

        # Test base64 voice cloning
        service = AudioService(
            config=AudioConfig(
                enabled=True,
                endpoint="http://mock-audio:8080",
                voice_cloning_enabled=True,
            ),
            client=client,
        )

        await service.synthesize(
            "Greetings traveler.",
            voice_ref_base64="dGVzdGF1ZGlv",
            reference_text="Sample voice reference.",
        )

        assert len(recorded_bodies) == 1
        assert recorded_bodies[0]["voice_ref"] == {"type": "base64", "data": "dGVzdGF1ZGlv"}
        assert recorded_bodies[0]["reference_text"] == "Sample voice reference."

        # Test server-side path voice reference
        service_path = AudioService(
            config=AudioConfig(
                enabled=True,
                endpoint="http://mock-audio:8080",
                voice_cloning_enabled=True,
                dm_voice_reference_path="/voices/dm.wav",
                dm_voice_reference_text="Reference text for DM.",
            ),
            client=client,
        )

        await service_path.synthesize("Welcome to the dungeon.")
        assert len(recorded_bodies) == 2
        assert recorded_bodies[1]["voice_ref"] == {"type": "path", "path": "/voices/dm.wav"}
        assert recorded_bodies[1]["reference_text"] == "Reference text for DM."

    asyncio.run(run())


def test_audio_service_transcribe() -> None:
    """transcribe sends multipart payload and extracts transcribed text."""

    async def run():
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/v1/audio/transcriptions"
            assert "multipart/form-data" in request.headers["content-type"]
            return httpx.Response(200, json={"text": "I search for secret doors."})

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        service = AudioService(
            config=AudioConfig(
                enabled=True,
                endpoint="http://mock-audio:8080",
                stt_model="qwen3-asr",
            ),
            client=client,
        )

        with pytest.raises(AudioTranscriptionError, match="empty audio payload"):
            await service.transcribe(b"")

        text = await service.transcribe(b"AUDIO_DATA", filename="player.wav")
        assert text == "I search for secret doors."

    asyncio.run(run())


def test_audio_api_endpoints_disabled() -> None:
    """Audio API endpoints reject operations gracefully when disabled."""
    with TestClient(app) as client:
        # Status returns enabled=False
        status_res = client.get("/api/audio/status")
        assert status_res.status_code == 200
        data = status_res.json()
        assert data["enabled"] is False
        assert data["healthy"] is False

        # Models returns 400
        models_res = client.get("/api/audio/models")
        assert models_res.status_code == 400
        assert "not enabled" in models_res.json()["detail"]

        # Speech returns 400
        speech_res = client.post("/api/audio/speech", json={"text": "Hello"})
        assert speech_res.status_code == 400
        assert "not enabled" in speech_res.json()["detail"]

        # Transcribe returns 400
        trans_res = client.post(
            "/api/audio/transcribe",
            files={"file": ("test.wav", b"dummy audio", "audio/wav")},
        )
        assert trans_res.status_code == 400
        assert "not enabled" in trans_res.json()["detail"]


def test_audio_api_endpoints_enabled(monkeypatch) -> None:
    """Audio API endpoints function properly when enabled with backend responses."""

    def mock_handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        if path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "pocket-tts"}, {"id": "qwen3-asr"}]})
        if path == "/v1/audio/speech":
            return httpx.Response(
                200, content=b"RIFFWAVEAUDIO", headers={"Content-Type": "audio/wav"}
            )
        if path == "/v1/audio/transcriptions":
            return httpx.Response(200, json={"text": "I attack the goblin with my sword."})
        return httpx.Response(404)

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
    mock_config = AudioConfig(
        enabled=True,
        endpoint="http://mock-audio:8080",
        tts_model="pocket-tts",
        stt_model="qwen3-asr",
    )
    mock_service = AudioService(config=mock_config, client=mock_client)

    with TestClient(app) as client:
        # Override the audio service on app state for testing enabled state
        client.app.state.audio_service = mock_service

        status_res = client.get("/api/audio/status")
        assert status_res.status_code == 200
        data = status_res.json()
        assert data["enabled"] is True
        assert data["healthy"] is True
        assert data["tts_model"] == "pocket-tts"

        models_res = client.get("/api/audio/models")
        assert models_res.status_code == 200
        assert models_res.json()["models"] == ["pocket-tts", "qwen3-asr"]

        speech_res = client.post("/api/audio/speech", json={"text": "The goblin collapses."})
        assert speech_res.status_code == 200
        assert speech_res.headers["content-type"] == "audio/wav"
        assert speech_res.content == b"RIFFWAVEAUDIO"

        trans_res = client.post(
            "/api/audio/transcribe",
            files={"file": ("attack.wav", b"VOICE_BYTES", "audio/wav")},
        )
        assert trans_res.status_code == 200
        assert trans_res.json()["text"] == "I attack the goblin with my sword."
