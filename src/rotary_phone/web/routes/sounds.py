"""Sound management routes."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Iterator, List

from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from rotary_phone.config.config_manager import ConfigError
from rotary_phone.web.models import AudioGainUpdate, RingSettingsUpdate, SoundAssignmentsUpdate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["sounds"])


def _validate_sound_filename(filename: str, sounds_dir: Path) -> Path:
    """Validate a sound filename and return the resolved path.

    Uses resolved path comparison to prevent path traversal attacks.

    Args:
        filename: The filename to validate
        sounds_dir: The sounds directory path

    Returns:
        Resolved file path if valid

    Raises:
        HTTPException: If filename is invalid or attempts path traversal
    """
    if not filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    sounds_dir_resolved = sounds_dir.resolve()
    file_path = (sounds_dir / filename).resolve()

    try:
        file_path.relative_to(sounds_dir_resolved)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid filename") from None

    return file_path


@router.get("/sounds")
async def list_sounds() -> Dict[str, List[Dict[str, Any]]]:
    """List all sound files in the sounds directory."""
    sounds_dir = Path("sounds")
    if not sounds_dir.exists():
        return {"files": []}

    files = []
    for sound_file in sorted(sounds_dir.glob("*.wav")):
        files.append(
            {
                "name": sound_file.name,
                "size": sound_file.stat().st_size,
                "path": str(sound_file),
            }
        )

    return {"files": files}


@router.post("/sounds/upload")
async def upload_sound(file: UploadFile) -> Dict[str, Any]:
    """Upload a new sound file."""
    if not file.filename or not file.filename.lower().endswith(".wav"):
        raise HTTPException(status_code=400, detail="Only .wav files are allowed")

    sounds_dir = Path("sounds")
    sounds_dir.mkdir(exist_ok=True)

    try:
        file_path = sounds_dir / file.filename
        content = await file.read()

        if not content.startswith(b"RIFF"):
            raise HTTPException(status_code=400, detail="Invalid WAV file format")

        file_path.write_bytes(content)

        return {
            "success": True,
            "message": f"File '{file.filename}' uploaded successfully",
            "filename": file.filename,
            "size": len(content),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload file: {e}") from e


@router.get("/sounds/{filename}")
async def get_sound(filename: str) -> StreamingResponse:
    """Stream a sound file for playback."""
    sounds_dir = Path("sounds")
    file_path = _validate_sound_filename(filename, sounds_dir)

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Sound file not found: {filename}")

    if not file_path.suffix.lower() == ".wav":
        raise HTTPException(status_code=400, detail="Only .wav files are supported")

    def iterfile() -> Iterator[bytes]:
        with open(file_path, "rb") as f:
            yield from f

    safe_filename = file_path.name
    return StreamingResponse(
        iterfile(),
        media_type="audio/wav",
        headers={"Content-Disposition": f"inline; filename={safe_filename}"},
    )


@router.delete("/sounds/{filename}")
async def delete_sound(request: Request, filename: str) -> Dict[str, Any]:
    """Delete a sound file."""
    sounds_dir = Path("sounds")
    file_path = _validate_sound_filename(filename, sounds_dir)

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Sound file not found: {filename}")

    audio_config: Dict[str, str] = request.app.state.config_manager.get("audio", {})
    assigned_to = []
    for key, value in audio_config.items():
        if value and Path(value).name == filename:
            assigned_to.append(key)

    try:
        file_path.unlink()
        return {
            "success": True,
            "message": f"Sound file '{filename}' deleted",
            "was_assigned_to": assigned_to,
        }
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete file: {e}") from e


@router.get("/sound-assignments")
async def get_sound_assignments(request: Request) -> Dict[str, Any]:
    """Get current sound assignments from config."""
    audio_config: Dict[str, str] = request.app.state.config_manager.get("audio", {})
    return {
        "assignments": {
            "ring_sound": audio_config.get("ring_sound", ""),
            "dial_tone": audio_config.get("dial_tone", ""),
            "busy_tone": audio_config.get("busy_tone", ""),
            "error_tone": audio_config.get("error_tone", ""),
        }
    }


@router.put("/sound-assignments")
async def update_sound_assignments(
    request: Request, data: SoundAssignmentsUpdate
) -> Dict[str, Any]:
    """Update sound assignments."""
    sounds_dir = Path("sounds")
    assignments = data.assignments.model_dump()

    # Validate sound files exist
    for key, value in assignments.items():
        if value and not (sounds_dir / Path(value).name).exists():
            if not Path(value).exists():
                raise HTTPException(
                    status_code=400,
                    detail=f"Sound file not found for '{key}': {value}",
                )

    try:
        current_audio: Dict[str, str] = request.app.state.config_manager.get("audio", {})
        for key, value in assignments.items():
            current_audio[key] = value

        request.app.state.config_manager.update_config({"audio": current_audio})
        request.app.state.config_manager.save_config(request.app.state.config_path)

        return {
            "success": True,
            "message": "Sound assignments updated successfully",
            "assignments": {
                "ring_sound": current_audio.get("ring_sound", ""),
                "dial_tone": current_audio.get("dial_tone", ""),
                "busy_tone": current_audio.get("busy_tone", ""),
                "error_tone": current_audio.get("error_tone", ""),
            },
        }
    except ConfigError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save assignments: {e}") from e


@router.get("/ring-settings")
async def get_ring_settings(request: Request) -> Dict[str, Any]:
    """Get ring timing settings."""
    timing = request.app.state.config_manager.get_timing_config()
    return {
        "ring_duration": timing.get("ring_duration", 2.0),
        "ring_pause": timing.get("ring_pause", 4.0),
    }


@router.put("/ring-settings")
async def update_ring_settings(request: Request, data: RingSettingsUpdate) -> Dict[str, Any]:
    """Update ring timing settings."""
    try:
        current_timing = request.app.state.config_manager.get_timing_config()

        if data.ring_duration is not None:
            current_timing["ring_duration"] = float(data.ring_duration)
        if data.ring_pause is not None:
            current_timing["ring_pause"] = float(data.ring_pause)

        request.app.state.config_manager.update_config({"timing": current_timing})
        request.app.state.config_manager.save_config(request.app.state.config_path)

        return {
            "success": True,
            "message": "Ring settings updated successfully",
            "ring_duration": current_timing.get("ring_duration", 2.0),
            "ring_pause": current_timing.get("ring_pause", 4.0),
        }
    except ConfigError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save ring settings: {e}") from e


@router.get("/audio-gain")
async def get_audio_gain(request: Request) -> Dict[str, Any]:
    """Get audio input/output gain settings."""
    audio_config: Dict[str, Any] = request.app.state.config_manager.get("audio", {})
    return {
        "input_gain": audio_config.get("input_gain", 1.0),
        "output_volume": audio_config.get("output_volume", 1.0),
    }


@router.put("/audio-gain")
async def update_audio_gain(request: Request, data: AudioGainUpdate) -> Dict[str, Any]:
    """Update audio gain settings."""
    try:
        current_audio: Dict[str, Any] = request.app.state.config_manager.get("audio", {})

        if data.input_gain is not None:
            current_audio["input_gain"] = float(data.input_gain)
        if data.output_volume is not None:
            current_audio["output_volume"] = float(data.output_volume)

        request.app.state.config_manager.update_config({"audio": current_audio})
        request.app.state.config_manager.save_config(request.app.state.config_path)

        return {
            "success": True,
            "message": "Audio gain settings updated successfully",
            "input_gain": current_audio.get("input_gain", 1.0),
            "output_volume": current_audio.get("output_volume", 1.0),
        }
    except ConfigError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to save audio gain settings: {e}"
        ) from e
