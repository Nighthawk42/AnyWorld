"""Client service for audio.cpp server (TTS, ASR/STT, and Voice Cloning)."""

import logging
from typing import Any
import httpx

from core.config import AudioConfig, settings

logger = logging.getLogger(__name__)


class AudioServiceError(Exception):
    """Base exception for audio service errors."""


class AudioServiceUnavailableError(AudioServiceError):
    """Raised when the audio.cpp server cannot be reached."""


class AudioSynthesisError(AudioServiceError):
    """Raised when text-to-speech synthesis fails."""


class AudioTranscriptionError(AudioServiceError):
    """Raised when audio transcription (STT/ASR) fails."""


class AudioService:
    """Async client service communicating with audio.cpp endpoints."""

    def __init__(
        self,
        config: AudioConfig | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """Initialize the audio service with configuration and optional HTTP client."""
        self.config = config or settings.audio
        self._owned_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(self.config.request_timeout_seconds)
        )

    @property
    def is_enabled(self) -> bool:
        """Return whether audio service integration is enabled."""
        return self.config.enabled

    @property
    def endpoint(self) -> str:
        """Return the base endpoint URL, stripped of trailing slashes."""
        return self.config.endpoint.rstrip("/")

    def _headers(self) -> dict[str, str]:
        """Construct request headers including authorization if configured."""
        headers = {}
        if self.config.api_key and self.config.api_key != "sk-no-key-required":
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        return headers

    async def check_health(self) -> bool:
        """Check if the audio.cpp server is reachable and responsive."""
        if not self.is_enabled:
            return False
        try:
            response = await self._client.get(
                f"{self.endpoint}/health",
                headers=self._headers(),
                timeout=5.0,
            )
            if response.status_code == 200:
                return True
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError):
            pass

        try:
            response = await self._client.get(
                f"{self.endpoint}/v1/models",
                headers=self._headers(),
                timeout=5.0,
            )
            return response.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError):
            return False

    async def list_models(self) -> list[str]:
        """Query available models registered on the audio.cpp server."""
        if not self.is_enabled:
            return []
        try:
            response = await self._client.get(
                f"{self.endpoint}/v1/models",
                headers=self._headers(),
            )
            response.raise_for_status()
            data = response.json()
            if isinstance(data, dict) and "data" in data:
                return [m["id"] for m in data["data"] if isinstance(m, dict) and "id" in m]
            if isinstance(data, list):
                return [m.get("id", str(m)) if isinstance(m, dict) else str(m) for m in data]
            return []
        except httpx.ConnectError as exc:
            raise AudioServiceUnavailableError("audio.cpp server is unreachable.") from exc
        except httpx.HTTPError as exc:
            raise AudioServiceError(f"Failed to list models: {exc}") from exc

    async def synthesize(
        self,
        text: str,
        *,
        voice: str | None = None,
        speed: float | None = None,
        voice_ref_base64: str | None = None,
        reference_text: str | None = None,
        model: str | None = None,
    ) -> bytes:
        """Synthesize text into speech audio using /v1/audio/speech.

        Supports standard voice presets and inline zero-shot voice cloning
        via reference audio.
        """
        if not self.is_enabled:
            raise AudioServiceError("Audio service is disabled in configuration.")
        if not text or not text.strip():
            raise AudioSynthesisError("Cannot synthesize empty text.")

        payload: dict[str, Any] = {
            "model": model or self.config.tts_model,
            "input": text.strip(),
            "speed": speed if speed is not None else self.config.speaking_rate,
        }
        selected_voice = voice or self.config.default_voice
        if selected_voice:
            payload["voice"] = selected_voice

        # Voice cloning / voice design reference handling
        if voice_ref_base64 and self.config.voice_cloning_enabled:
            payload["voice_ref"] = {"type": "base64", "data": voice_ref_base64}
            if reference_text:
                payload["reference_text"] = reference_text
        elif self.config.voice_cloning_enabled and self.config.dm_voice_reference_path:
            payload["voice_ref"] = {
                "type": "path",
                "path": self.config.dm_voice_reference_path,
            }
            if self.config.dm_voice_reference_text:
                payload["reference_text"] = self.config.dm_voice_reference_text

        headers = {**self._headers(), "Content-Type": "application/json"}
        try:
            response = await self._client.post(
                f"{self.endpoint}/v1/audio/speech",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            return response.content
        except httpx.ConnectError as exc:
            raise AudioServiceUnavailableError("audio.cpp server is unreachable.") from exc
        except httpx.HTTPStatusError as exc:
            raise AudioSynthesisError(
                f"TTS synthesis failed with status {exc.response.status_code}: {exc.response.text}"
            ) from exc
        except httpx.HTTPError as exc:
            raise AudioSynthesisError(f"TTS request failed: {exc}") from exc

    async def transcribe(
        self,
        audio_bytes: bytes,
        *,
        filename: str = "audio.wav",
        content_type: str = "audio/wav",
        model: str | None = None,
        language: str | None = None,
        prompt: str | None = None,
    ) -> str:
        """Transcribe speech audio to text using /v1/audio/transcriptions."""
        if not self.is_enabled:
            raise AudioServiceError("Audio service is disabled in configuration.")
        if not audio_bytes:
            raise AudioTranscriptionError("Cannot transcribe empty audio payload.")

        data: dict[str, Any] = {
            "model": model or self.config.stt_model,
        }
        if language:
            data["language"] = language
        if prompt:
            data["prompt"] = prompt

        files = {
            "file": (filename, audio_bytes, content_type),
        }
        headers = self._headers()
        try:
            response = await self._client.post(
                f"{self.endpoint}/v1/audio/transcriptions",
                data=data,
                files=files,
                headers=headers,
            )
            response.raise_for_status()
            result = response.json()
            if isinstance(result, dict) and "text" in result:
                return result["text"].strip()
            return str(result).strip()
        except httpx.ConnectError as exc:
            raise AudioServiceUnavailableError("audio.cpp server is unreachable.") from exc
        except httpx.HTTPStatusError as exc:
            raise AudioTranscriptionError(
                f"Transcription failed with status {exc.response.status_code}: {exc.response.text}"
            ) from exc
        except httpx.HTTPError as exc:
            raise AudioTranscriptionError(f"Transcription request failed: {exc}") from exc

    async def run_task(
        self,
        model: str,
        request_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a specialized audio task via /v1/tasks/run."""
        if not self.is_enabled:
            raise AudioServiceError("Audio service is disabled in configuration.")

        payload = {
            "model": model,
            "request": request_data,
        }
        headers = {**self._headers(), "Content-Type": "application/json"}
        try:
            response = await self._client.post(
                f"{self.endpoint}/v1/tasks/run",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            return response.json()
        except httpx.ConnectError as exc:
            raise AudioServiceUnavailableError("audio.cpp server is unreachable.") from exc
        except httpx.HTTPError as exc:
            raise AudioServiceError(f"Task execution failed: {exc}") from exc

    async def close(self) -> None:
        """Close the underlying HTTP client if owned by this instance."""
        if self._owned_client and self._client is not None:
            await self._client.aclose()
