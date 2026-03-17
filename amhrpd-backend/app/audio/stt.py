import numpy as np
import whisper
from scipy.signal import resample

_model = None

def _get_model(model_name: str = "base"):
    global _model
    if _model is None:
        _model = whisper.load_model(model_name)
    return _model

def transcribe_pcm(pcm_bytes: bytes, samplerate: int = 16000, model_name: str = "base") -> str:
    if not pcm_bytes:
        return ""
    audio = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    if samplerate != 16000:
        new_len = int(len(audio) * 16000 / samplerate)
        audio = resample(audio, new_len)
    model = _get_model(model_name)
    result = model.transcribe(audio, fp16=False)
    print(result.get("text", "").strip())
    return result.get("text", "")
