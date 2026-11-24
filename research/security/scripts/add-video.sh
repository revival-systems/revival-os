#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 2 ]; then
    echo "Usage: $0 VIDEO_NAME YOUTUBE_URL"
    exit 1
fi

NAME="$1"
URL="$2"

case "$NAME" in
    *[!a-zA-Z0-9_-]*|"")
        echo "Use letters, numbers, hyphens or underscores."
        exit 1
        ;;
esac

DIR="videos/$NAME"
mkdir -p "$DIR"

cat > "$DIR/source.md" <<META
# $NAME

Original video: $URL

## Research questions

- Which operating system layer is targeted?
- What vulnerability class is involved?
- Which security boundary is crossed?
- How could Revival OS defend against it?
- Which tests should we implement?

## Findings

Not reviewed yet.
META

echo "Downloading video..."

yt-dlp \
    --no-playlist \
    -f 'bv*[ext=mp4][height<=720]+ba[ext=m4a]/b[ext=mp4][height<=720]/best' \
    --merge-output-format mp4 \
    --remux-video mp4 \
    -o "$DIR/video.%(ext)s" \
    "$URL"

if [ ! -f "$DIR/video.mp4" ]; then
    echo "Expected MP4 not found. Check download output."
    exit 1
fi

echo "Extracting audio..."

ffmpeg -hide_banner -loglevel error -y \
    -i "$DIR/video.mp4" \
    -vn -ac 1 -ar 16000 \
    "$DIR/audio.wav"

echo "Transcribing with Whisper..."

whisper "$DIR/audio.wav" \
    --model small.en \
    --language English \
    --fp16 False \
    --output_format all \
    --output_dir "$DIR"

for ext in txt srt vtt tsv json; do
    mv "$DIR/audio.$ext" "$DIR/transcript.$ext"
done

rm "$DIR/audio.wav"

echo "Complete: $DIR"
