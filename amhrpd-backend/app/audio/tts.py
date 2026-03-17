import os
import tempfile
import numpy as np
import soundfile as sf
import pyttsx3
from scipy.signal import resample

def tts_to_pcm(text: str, target_sr: int = 16000) -> bytes:
    if not text:
        return b""
    engine = pyttsx3.init()
    engine.setProperty("rate", 150)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
        wav_path = f.name
    engine.save_to_file(text, wav_path)
    engine.runAndWait()
    audio, sr = sf.read(wav_path, dtype="float32")
    os.remove(wav_path)
    if audio.ndim == 2:
        audio = np.mean(audio, axis=1)
    if sr != target_sr:
        new_len = int(len(audio) * target_sr / sr)
        audio = resample(audio, new_len)
    audio = np.clip(audio, -1.0, 1.0)
    pcm_int16 = (audio * 32767).astype(np.int16)
    return pcm_int16.tobytes()
