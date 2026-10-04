"""FastAPI endpoints for audio services (TTS, ASR/STT, and Voice Cloning)."""

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from pydantic import BaseModel, Field

from logic.audio import (
    AudioService,
    AudioServiceError,
    AudioServiceUnavailableError,
    AudioSynthesisError,
    AudioTranscriptionError,
)

router = APIRouter(prefix="/api/audio", tags=["audio"])


def get_audio_service(request: Request) -> AudioService:
    """Retrieve the AudioService instance from the application state."""
    service = getattr(request.app.state, "audio_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Audio service is not initialized.",
        )
    return service


class SpeechRequest(BaseModel):
    """Payload for text-to-speech requests."""

    text: str = Field(..., min_length=1, max_length=10000, description="Text to synthesize")
    voice: str | None = Field(default=None, description="Voice identifier or preset")
    speed: float | None = Field(
        default=None, ge=0.25, le=4.0, description="Speaking rate multiplier"
    )
    voice_ref_base64: str | None = Field(
        default=None, description="Base64-encoded audio for zero-shot voice cloning"
    )
    reference_text: str | None = Field(
        default=None, description="Transcript of the voice reference audio"
    )
    model: str | None = Field(default=None, description="TTS model override")


class AudioStatusResponse(BaseModel):
    """Audio service operational status."""

    enabled: bool
    healthy: bool
    endpoint: str
    tts_model: str
    stt_model: str
    voice_cloning_enabled: bool
    default_voice: str | None = None


class AudioModelsResponse(BaseModel):
    """List of available models registered on the audio backend."""

    models: list[str]


class AudioTranscriptionResponse(BaseModel):
    """Transcription result from speech-to-text processing."""

    text: str


@router.get("/status", response_model=AudioStatusResponse)
async def get_audio_status(
    service: AudioService = Depends(get_audio_service),
) -> AudioStatusResponse:
    """Return health and capabilities of the audio backend."""
    healthy = False
    if service.is_enabled:
        healthy = await service.check_health()
    return AudioStatusResponse(
        enabled=service.is_enabled,
        healthy=healthy,
        endpoint=service.endpoint,
        tts_model=service.config.tts_model,
        stt_model=service.config.stt_model,
        voice_cloning_enabled=service.config.voice_cloning_enabled,
        default_voice=service.config.default_voice,
    )


@router.get("/models", response_model=AudioModelsResponse)
async def get_audio_models(
    service: AudioService = Depends(get_audio_service),
) -> AudioModelsResponse:
    """List available audio models on the backend."""
    if not service.is_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Audio service is not enabled.",
        )
    try:
        models = await service.list_models()
        return AudioModelsResponse(models=models)
    except AudioServiceUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except AudioServiceError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.post("/speech")
async def generate_speech(
    body: SpeechRequest,
    service: AudioService = Depends(get_audio_service),
) -> Response:
    """Synthesize text to speech audio."""
    if not service.is_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Audio service is not enabled.",
        )
    try:
        audio_bytes = await service.synthesize(
            text=body.text,
            voice=body.voice,
            speed=body.speed,
            voice_ref_base64=body.voice_ref_base64,
            reference_text=body.reference_text,
            model=body.model,
        )
        return Response(content=audio_bytes, media_type="audio/wav")
    except AudioServiceUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except AudioSynthesisError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except AudioServiceError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.post("/transcribe", response_model=AudioTranscriptionResponse)
async def transcribe_audio(
    file: UploadFile = File(...),
    model: str | None = Form(default=None),
    language: str | None = Form(default=None),
    prompt: str | None = Form(default=None),
    service: AudioService = Depends(get_audio_service),
) -> AudioTranscriptionResponse:
    """Transcribe uploaded audio file to text."""
    if not service.is_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Audio service is not enabled.",
        )
    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No audio data received.",
        )
    try:
        text = await service.transcribe(
            audio_bytes,
            filename=file.filename or "audio.wav",
            content_type=file.content_type or "audio/wav",
            model=model,
            language=language,
            prompt=prompt,
        )
        return AudioTranscriptionResponse(text=text)
    except AudioServiceUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except AudioTranscriptionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except AudioServiceError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
