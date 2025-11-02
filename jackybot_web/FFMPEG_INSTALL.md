# Video Compression - Client-Side Processing

**Note:** Video compression now happens entirely in the browser using FFmpeg.wasm. No server-side FFmpeg installation is required!

## How It Works

- All video processing happens locally in your browser
- Videos never leave your device
- Uses FFmpeg.wasm (WebAssembly port of FFmpeg)
- Automatic download of compressed files

## Browser Requirements

- Modern browser with WebAssembly support
- Sufficient RAM for video processing (varies by video size)
- JavaScript enabled

## Troubleshooting

If compression fails:
1. Try a smaller video file (< 1GB)
2. Ensure you have enough free RAM
3. Try a different browser (Chrome recommended)
4. Check browser console for errors

## Technical Details

- Uses @ffmpeg/ffmpeg library for browser-based video processing
- Supports MP4 and MOV input formats
- Outputs AV1 video in MP4 container or AVIF image sequence
- Automatic 60-second trimming
- File size limited to 8MB maximum
