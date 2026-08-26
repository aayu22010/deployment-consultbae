"""
Audio Analyzer Module
=====================
Extracts audio properties from files without requiring ffmpeg.
Supports WAV natively; uses mutagen for other formats.

Properties extracted:
  - duration (seconds)
  - sample_rate (kHz)
  - bitrate (kbps)
  - loudness (dBFS via RMS)
  - noise_estimate ('clean', 'moderate_noise', 'noisy')
"""

import os
import struct
import wave
import math
import numpy as np

# Try to import mutagen for non-WAV formats
try:
    import mutagen
    HAS_MUTAGEN = True
except ImportError:
    HAS_MUTAGEN = False


def analyze_audio(filepath: str) -> dict:
    """
    Analyze an audio file and return its properties.
    Returns a dict with: duration_seconds, sample_rate_khz,
    bitrate_kbps, loudness_db, noise_estimate.
    """
    ext = os.path.splitext(filepath)[1].lower()

    if ext == ".wav":
        return _analyze_wav(filepath)
    elif HAS_MUTAGEN:
        return _analyze_with_mutagen(filepath)
    else:
        return _analyze_fallback(filepath)


def _analyze_wav(filepath: str) -> dict:
    """Analyze a WAV file using Python's built-in wave module + numpy."""
    result = {
        "duration_seconds": 0.0,
        "sample_rate_khz": 0.0,
        "bitrate_kbps": 0.0,
        "loudness_db": -100.0,
        "noise_estimate": "unknown",
    }

    try:
        with wave.open(filepath, "rb") as wf:
            n_channels = wf.getnchannels()
            sample_width = wf.getsampwidth()  # bytes per sample
            frame_rate = wf.getframerate()
            n_frames = wf.getnframes()

            # Duration
            duration = n_frames / frame_rate if frame_rate > 0 else 0
            result["duration_seconds"] = round(duration, 2)

            # Sample rate in kHz
            result["sample_rate_khz"] = round(frame_rate / 1000, 1)

            # Bitrate: sample_rate * channels * bits_per_sample
            bits_per_sample = sample_width * 8
            bitrate = frame_rate * n_channels * bits_per_sample / 1000
            result["bitrate_kbps"] = round(bitrate, 1)

            # Read raw audio data for loudness/noise analysis
            raw_data = wf.readframes(n_frames)

            if len(raw_data) > 0 and n_frames > 0:
                # Convert raw bytes to numpy array
                samples = _bytes_to_samples(raw_data, sample_width, n_channels)

                if len(samples) > 0:
                    # Loudness (dBFS via RMS)
                    result["loudness_db"] = _compute_loudness_dbfs(samples)

                    # Noise estimate
                    result["noise_estimate"] = _estimate_noise(
                        samples, frame_rate)

    except Exception as e:
        print(f"  [WARN] WAV analysis error: {e}")

    return result


def _analyze_with_mutagen(filepath: str) -> dict:
    """Analyze non-WAV audio using mutagen for metadata."""
    result = {
        "duration_seconds": 0.0,
        "sample_rate_khz": 0.0,
        "bitrate_kbps": 0.0,
        "loudness_db": -100.0,
        "noise_estimate": "unknown",
    }

    try:
        audio = mutagen.File(filepath)
        if audio is None:
            return _analyze_fallback(filepath)

        # Duration
        if hasattr(audio.info, "length"):
            result["duration_seconds"] = round(audio.info.length, 2)

        # Sample rate
        if hasattr(audio.info, "sample_rate"):
            result["sample_rate_khz"] = round(
                audio.info.sample_rate / 1000, 1)

        # Bitrate
        if hasattr(audio.info, "bitrate"):
            result["bitrate_kbps"] = round(audio.info.bitrate / 1000, 1)
        elif result["duration_seconds"] > 0:
            # Estimate from file size
            file_size = os.path.getsize(filepath)
            result["bitrate_kbps"] = round(
                file_size * 8 / result["duration_seconds"] / 1000, 1)

        # For loudness and noise, try to read raw audio
        # With mutagen we can't easily get raw samples,
        # so estimate from file characteristics
        result["loudness_db"] = _estimate_loudness_from_file(filepath)
        result["noise_estimate"] = "unknown"

    except Exception as e:
        print(f"  [WARN] Mutagen analysis error: {e}")
        return _analyze_fallback(filepath)

    return result


def _analyze_fallback(filepath: str) -> dict:
    """Fallback analysis when no specialized library is available."""
    file_size = os.path.getsize(filepath)
    return {
        "duration_seconds": 0.0,
        "sample_rate_khz": 0.0,
        "bitrate_kbps": 0.0,
        "loudness_db": -100.0,
        "noise_estimate": "unknown",
    }


def _bytes_to_samples(raw_data: bytes, sample_width: int,
                       n_channels: int) -> np.ndarray:
    """Convert raw WAV bytes to a numpy float array (mono, -1.0 to 1.0)."""
    if sample_width == 1:
        # 8-bit unsigned
        samples = np.frombuffer(raw_data, dtype=np.uint8).astype(np.float64)
        samples = (samples - 128) / 128.0
    elif sample_width == 2:
        # 16-bit signed (most common)
        samples = np.frombuffer(raw_data, dtype=np.int16).astype(np.float64)
        samples = samples / 32768.0
    elif sample_width == 3:
        # 24-bit signed — unpack manually
        n_samples = len(raw_data) // 3
        samples = np.zeros(n_samples, dtype=np.float64)
        for i in range(n_samples):
            b = raw_data[i*3:(i+1)*3]
            val = struct.unpack("<i", b + (b"\xff" if b[2] & 0x80 else b"\x00"))[0]
            samples[i] = val / 8388608.0
    elif sample_width == 4:
        # 32-bit signed
        samples = np.frombuffer(raw_data, dtype=np.int32).astype(np.float64)
        samples = samples / 2147483648.0
    else:
        return np.array([])

    # Convert to mono by averaging channels
    if n_channels > 1:
        samples = samples.reshape(-1, n_channels).mean(axis=1)

    return samples


def _compute_loudness_dbfs(samples: np.ndarray) -> float:
    """Compute loudness in dBFS using RMS."""
    if len(samples) == 0:
        return -100.0

    # RMS (Root Mean Square)
    rms = np.sqrt(np.mean(samples ** 2))

    if rms < 1e-10:
        return -100.0

    # Convert to dBFS (decibels relative to full scale)
    dbfs = 20 * math.log10(rms)
    return round(dbfs, 1)


def _estimate_noise(samples: np.ndarray, sample_rate: int) -> str:
    """
    Estimate noise level using spectral flatness.

    Spectral flatness = geometric mean / arithmetic mean of power spectrum.
    - Values close to 1.0 = noise-like (flat spectrum)
    - Values close to 0.0 = tonal/clean (peaked spectrum)
    """
    if len(samples) < 256:
        return "unknown"

    try:
        # Use a window of the audio for FFT
        # Take multiple segments and average
        segment_size = min(4096, len(samples))
        n_segments = min(10, len(samples) // segment_size)

        if n_segments == 0:
            n_segments = 1
            segment_size = len(samples)

        flatness_values = []

        for i in range(n_segments):
            start = i * segment_size
            segment = samples[start:start + segment_size]

            # Apply Hanning window
            window = np.hanning(len(segment))
            windowed = segment * window

            # FFT
            spectrum = np.abs(np.fft.rfft(windowed))
            power = spectrum ** 2

            # Avoid log(0)
            power = np.maximum(power, 1e-20)

            # Spectral flatness
            log_mean = np.mean(np.log(power))
            geometric_mean = np.exp(log_mean)
            arithmetic_mean = np.mean(power)

            if arithmetic_mean > 0:
                flatness = geometric_mean / arithmetic_mean
                flatness_values.append(flatness)

        if not flatness_values:
            return "unknown"

        avg_flatness = np.mean(flatness_values)

        # Also compute the ratio of silence (samples near zero)
        silence_ratio = np.mean(np.abs(samples) < 0.01)

        # Classify
        if avg_flatness > 0.5 or silence_ratio > 0.8:
            return "noisy"
        elif avg_flatness > 0.15:
            return "moderate_noise"
        else:
            return "clean"

    except Exception:
        return "unknown"


def _estimate_loudness_from_file(filepath: str) -> float:
    """
    Try to estimate loudness by reading raw bytes and
    computing a rough RMS. Works for any file but less accurate.
    """
    try:
        file_size = os.path.getsize(filepath)
        # Read a chunk from the middle of the file
        chunk_size = min(65536, file_size)
        with open(filepath, "rb") as f:
            # Skip to 25% of file (past headers)
            f.seek(file_size // 4)
            data = f.read(chunk_size)

        if len(data) < 100:
            return -100.0

        # Interpret as 16-bit samples (rough approximation)
        n_samples = len(data) // 2
        samples = np.frombuffer(data[:n_samples * 2],
                                dtype=np.int16).astype(np.float64)
        samples = samples / 32768.0

        return _compute_loudness_dbfs(samples)

    except Exception:
        return -100.0


# ── Quick self-test ──
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        result = analyze_audio(sys.argv[1])
        print(f"  Duration:     {result['duration_seconds']} s")
        print(f"  Sample rate:  {result['sample_rate_khz']} kHz")
        print(f"  Bitrate:      {result['bitrate_kbps']} kbps")
        print(f"  Loudness:     {result['loudness_db']} dBFS")
        print(f"  Noise est.:   {result['noise_estimate']}")
    else:
        print("Usage: python audio_analyzer.py <audio_file>")
