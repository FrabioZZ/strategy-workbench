"""Catch PyAV/faster-whisper incompatibility before loading model weights."""
import wave

import numpy as np
from faster_whisper.audio import decode_audio


def test_asr_decoder_accepts_real_pcm_wave(tmp_path):
    # PyAV 19 rejects the metadata_errors argument used by faster-whisper 1.2.1.
    # A real one-second PCM file checks this dependency boundary without a model.
    path = tmp_path / 'speech-decoder.wav'
    with wave.open(str(path), 'wb') as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(b'\x00\x20' * 16000)

    audio = decode_audio(str(path))

    assert audio.shape == (16000,)
    assert audio.dtype == np.float32
    assert np.allclose(audio, 0.25)
