#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "Usage: bash research/security/scripts/transcribe-local-video.sh /path/to/video.mp4 [folder-name]" >&2
  exit 2
fi

INPUT="$1"
NAME="${2:-06-landfall-blackhat-2026}"
[[ -f "$INPUT" ]] || { echo "File not found: $INPUT" >&2; exit 1; }
case "$NAME" in
  ""|*[!a-zA-Z0-9_-]*) echo "Invalid folder name: $NAME" >&2; exit 2 ;;
esac
command -v ffmpeg >/dev/null || { echo "ffmpeg missing; install with brew install ffmpeg" >&2; exit 1; }
command -v whisper >/dev/null || { echo "whisper missing; activate the Python .venv containing openai-whisper" >&2; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SECURITY_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DIR="$SECURITY_DIR/videos/$NAME"
mkdir -p "$DIR"

if [[ ! -f "$DIR/video.mp4" ]]; then
  cp "$INPUT" "$DIR/video.mp4"
fi

if [[ -f "$DIR/transcript.txt" ]]; then
  echo "Already transcribed: $DIR/transcript.txt"
  exit 0
fi

ffmpeg -hide_banner -loglevel error -y -i "$DIR/video.mp4" \
  -vn -ac 1 -ar 16000 "$DIR/audio.wav"

whisper "$DIR/audio.wav" \
  --model "${WHISPER_MODEL:-small.en}" \
  --language English --fp16 False \
  --output_format all --output_dir "$DIR"

for ext in txt srt vtt tsv json; do
  [[ -f "$DIR/audio.$ext" ]] && mv "$DIR/audio.$ext" "$DIR/transcript.$ext"
done

rm -f "$DIR/audio.wav"
echo "Transcript saved locally at: $DIR/transcript.txt"
echo "Media and transcription stay ignored by Git; keep permission requirements in mind."
