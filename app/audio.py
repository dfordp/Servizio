# audio.py
import audioop

SAMPLE_WIDTH = 2  # 16-bit
CHANNELS = 1
TWILIO_FRAME_BYTES = 160  # 20ms @ 8k μ-law

def ulaw8k_to_lin16_48k(ulaw_bytes: bytes, state):
    lin8k = audioop.ulaw2lin(ulaw_bytes, SAMPLE_WIDTH)
    lin48k, new_state = audioop.ratecv(lin8k, SAMPLE_WIDTH, CHANNELS, 8000, 48000, state)
    return lin48k, new_state

def lin16_24k_to_ulaw8k(lin24k_bytes: bytes, state):
    lin8k, new_state = audioop.ratecv(lin24k_bytes, SAMPLE_WIDTH, CHANNELS, 24000, 8000, state)
    ulaw8k = audioop.lin2ulaw(lin8k, SAMPLE_WIDTH)
    return ulaw8k, new_state

def chunk_bytes(b: bytes, size: int):
    for i in range(0, len(b), size):
        yield b[i:i+size]
