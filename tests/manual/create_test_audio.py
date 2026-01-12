"""Create a test audio file for VoIP testing.

This script generates a simple 8kHz, 16-bit, mono WAV file with
a tone that can be used to test audio transmission.

Run with:
    python -m tests.manual.create_test_audio
"""

import math
import struct
import wave


def create_tone_wav(filename: str, duration: float = 3.0, frequency: float = 440.0) -> None:
    """Create a WAV file with a sine wave tone.

    Args:
        filename: Output WAV filename
        duration: Duration in seconds
        frequency: Tone frequency in Hz (default 440 Hz = A4 note)
    """
    sample_rate = 8000  # 8kHz for VoIP
    num_channels = 1  # Mono
    sample_width = 2  # 16-bit
    num_frames = int(sample_rate * duration)

    print(f"Creating test audio file: {filename}")
    print(f"  Duration: {duration}s")
    print(f"  Frequency: {frequency} Hz")
    print(f"  Sample rate: {sample_rate} Hz")
    print(f"  Channels: {num_channels} (mono)")
    print(f"  Sample width: {sample_width * 8}-bit")

    # Generate sine wave samples
    samples = []
    for i in range(num_frames):
        # Calculate sample value
        t = i / sample_rate
        value = math.sin(2 * math.pi * frequency * t)

        # Convert to 16-bit signed integer
        sample = int(value * 32767)
        samples.append(sample)

    # Write to WAV file
    with wave.open(filename, "wb") as wav:
        wav.setnchannels(num_channels)
        wav.setsampwidth(sample_width)
        wav.setframerate(sample_rate)

        # Pack samples as 16-bit signed integers
        packed = struct.pack("<" + "h" * len(samples), *samples)
        wav.writeframes(packed)

    print(f"✓ Created {filename}")
    print(f"  File size: {len(packed)} bytes")
    print(f"  Duration: {len(samples) / sample_rate:.1f}s")


def create_speech_like_tone(filename: str, duration: float = 3.0) -> None:
    """Create a WAV file with multiple tones to sound more speech-like.

    Args:
        filename: Output WAV filename
        duration: Duration in seconds
    """
    sample_rate = 8000
    num_channels = 1
    sample_width = 2
    num_frames = int(sample_rate * duration)

    print(f"Creating speech-like test audio: {filename}")
    print(f"  Duration: {duration}s")

    # Use multiple frequencies (fundamental + harmonics)
    frequencies = [300, 600, 900, 1200]  # Hz
    amplitudes = [1.0, 0.5, 0.3, 0.2]  # Relative amplitudes

    samples = []
    for i in range(num_frames):
        t = i / sample_rate
        value = 0

        # Sum multiple sine waves
        for freq, amp in zip(frequencies, amplitudes):
            value += amp * math.sin(2 * math.pi * freq * t)

        # Normalize to prevent clipping
        value /= sum(amplitudes)

        # Apply simple envelope (fade in/out)
        envelope = 1.0
        fade_duration = 0.1  # 100ms fade
        fade_samples = int(sample_rate * fade_duration)
        if i < fade_samples:
            envelope = i / fade_samples
        elif i > num_frames - fade_samples:
            envelope = (num_frames - i) / fade_samples

        # Convert to 16-bit signed integer
        sample = int(value * envelope * 32767)
        samples.append(sample)

    # Write to WAV file
    with wave.open(filename, "wb") as wav:
        wav.setnchannels(num_channels)
        wav.setsampwidth(sample_width)
        wav.setframerate(sample_rate)
        packed = struct.pack("<" + "h" * len(samples), *samples)
        wav.writeframes(packed)

    print(f"✓ Created {filename}")


def main() -> None:
    """Create test audio files."""
    print("=" * 60)
    print("VoIP Test Audio Generator")
    print("=" * 60)
    print()

    # Create simple tone
    create_tone_wav("test_tone.wav", duration=3.0, frequency=440.0)
    print()

    # Create speech-like tone
    create_speech_like_tone("test_speech.wav", duration=3.0)
    print()

    print("=" * 60)
    print("Test files created successfully!")
    print()
    print("You can now use these files with:")
    print("  python -m tests.manual.test_real_phone")
    print()
    print("In the test harness, use the 'a' command and provide:")
    print("  test_tone.wav    - Simple 440 Hz tone")
    print("  test_speech.wav  - Multi-frequency tone (more speech-like)")
    print("=" * 60)


if __name__ == "__main__":
    main()
