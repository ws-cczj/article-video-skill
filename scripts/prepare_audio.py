"""Convert a recording or a video's default audio track to renderer-ready PCM WAV."""
import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile
import wave

from speech_io import normalize_pcm


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path, help='Audio or video input file')
    parser.add_argument('--output', required=True, type=Path, help='Output .wav file')
    parser.add_argument('--ffmpeg', default='ffmpeg', help='FFmpeg command or executable path')
    parser.add_argument('--overwrite', action='store_true', help='Replace an existing output file')
    args = parser.parse_args()
    source, destination = args.input.resolve(), args.output.resolve()
    if not source.is_file():
        parser.error(f'Input file does not exist: {source}')
    if destination.suffix.lower() != '.wav':
        parser.error('Output must use the .wav extension')
    if source == destination:
        parser.error('Input and output must be different files')
    if destination.exists() and (not args.overwrite or not destination.is_file()):
        parser.error('Output already exists; choose another path or use --overwrite for a file')
    ffmpeg = shutil.which(args.ffmpeg)
    if not ffmpeg:
        parser.error('FFmpeg not found. Run scripts/download_ffmpeg.ps1 or supply --ffmpeg PATH')
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        # Only publish a fully converted WAV; failures leave an existing output intact.
        with tempfile.TemporaryDirectory(prefix='prepare-audio-', dir=destination.parent) as temp:
            converted = normalize_pcm(source, Path(temp) / 'audio.wav', ffmpeg)
            with wave.open(str(converted), 'rb') as wav:
                duration = wav.getnframes() / wav.getframerate()
            converted.replace(destination)
    except subprocess.CalledProcessError as error:
        detail = error.stderr.decode('utf-8', errors='replace') if error.stderr else str(error)
        parser.exit(1, f'FFmpeg conversion failed: {detail.strip()}\n')
    except (OSError, ValueError, wave.Error, EOFError) as error:
        parser.exit(1, f'Audio preparation failed: {error}\n')
    print(f'Output: {destination}')
    print(f'Format: PCM signed 16-bit, 48000 Hz, mono; duration: {duration:.3f} s')


if __name__ == '__main__':
    main()
