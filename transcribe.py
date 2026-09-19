import io
import logging
import tempfile
import os

log = logging.getLogger(__name__)

_model = None


def _get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        model_size = os.getenv("WHISPER_MODEL", "base")
        log.info("Loading Whisper model '%s' (first call may download it)...", model_size)
        _model = WhisperModel(model_size, device="cpu", compute_type="int8")
        log.info("Whisper model loaded.")
    return _model


def transcribe_audio(audio_bytes: bytes, content_type: str = "audio/webm") -> str:
    ext = ".webm"
    if "wav" in content_type:
        ext = ".wav"
    elif "mp4" in content_type or "m4a" in content_type:
        ext = ".m4a"
    elif "ogg" in content_type:
        ext = ".ogg"

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
        f.write(audio_bytes)
        tmp_path = f.name

    try:
        model = _get_model()
        segments, info = model.transcribe(tmp_path, beam_size=5)
        text = " ".join(seg.text.strip() for seg in segments)
        return text.strip()
    finally:
        os.unlink(tmp_path)
