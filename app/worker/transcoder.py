import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Dict, Any, Union

from app.models.job import VideoQuality
from app.core.exceptions import InvalidMediaFileError, FFmpegExecutionError

logger = logging.getLogger(__name__)

QUALITY_HEIGHT_MAP: Dict[str, int] = {
    VideoQuality.Q_360P.value: 360,
    VideoQuality.Q_480P.value: 480,
    VideoQuality.Q_720P.value: 720,
    VideoQuality.Q_1080P.value: 1080,
    "360p": 360,
    "480p": 480,
    "720p": 720,
    "1080p": 1080,
}


class Transcoder:
    def __init__(self, ffmpeg_bin: str = "ffmpeg", ffprobe_bin: str = "ffprobe") -> None:
        self.ffmpeg_bin = ffmpeg_bin
        self.ffprobe_bin = ffprobe_bin

    def validate_media(self, filepath: str) -> Dict[str, Any]:
        """Inspects media file using ffprobe.
        Ensures the file is decodable and contains at least one valid video stream.
        """
        if not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
            raise InvalidMediaFileError(f"Media file does not exist or is empty: {filepath}")

        cmd = [
            self.ffprobe_bin,
            "-v",
            "error",
            "-show_entries",
            "format=duration,size,format_name:stream=codec_type,codec_name,width,height",
            "-of",
            "json",
            str(filepath),
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        except subprocess.TimeoutExpired as e:
            raise InvalidMediaFileError("ffprobe execution timed out validating media file") from e
        except Exception as e:
            raise InvalidMediaFileError(f"Failed to execute ffprobe: {e}") from e

        if result.returncode != 0:
            raise InvalidMediaFileError(f"Invalid or unreadable media file: {result.stderr.strip()}")

        try:
            metadata = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            raise InvalidMediaFileError("ffprobe returned unparseable metadata") from e

        streams = metadata.get("streams", [])
        has_video = any(s.get("codec_type") == "video" for s in streams)
        if not has_video:
            raise InvalidMediaFileError("Uploaded file does not contain a valid video stream")

        return metadata

    def transcode(
        self,
        input_path: str,
        output_path: str,
        target_quality: Union[str, VideoQuality],
        timeout_seconds: int = 1800,
    ) -> None:
        """Transcodes input video to target resolution using FFmpeg.
        Performs pre-validation and post-validation to ensure output stream integrity.
        """
        # 1. Pre-validation
        self.validate_media(input_path)

        # 2. Resolve target height
        quality_str = target_quality.value if isinstance(target_quality, VideoQuality) else str(target_quality)
        target_height = QUALITY_HEIGHT_MAP.get(quality_str, 720)

        # Ensure output directory exists
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        # 3. Build FFmpeg command
        # scale=-2:height guarantees width is an even number for H.264
        # -movflags +faststart enables web streaming by placing MOOV atom at head
        cmd = [
            self.ffmpeg_bin,
            "-y",  # Overwrite output without prompting
            "-i",
            str(input_path),
            "-vf",
            f"scale=-2:{target_height}",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "23",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            str(output_path),
        ]

        logger.info(f"Starting FFmpeg transcode: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as e:
            raise FFmpegExecutionError(
                f"Transcoding process timed out after {timeout_seconds} seconds"
            ) from e
        except Exception as e:
            raise FFmpegExecutionError(f"Failed to execute FFmpeg process: {e}") from e

        if result.returncode != 0:
            error_details = result.stderr.strip()
            raise FFmpegExecutionError(f"FFmpeg failed with exit code {result.returncode}: {error_details}")

        # 4. Post-validation: ensure output exists, non-empty, and decodable
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise FFmpegExecutionError("FFmpeg finished but output file is empty or missing")

        try:
            self.validate_media(output_path)
        except InvalidMediaFileError as e:
            raise FFmpegExecutionError(f"Transcoded output failed validation: {e}") from e
