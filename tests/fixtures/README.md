# Test Fixtures

Add a sample video file (`sample.mp4`) to this directory to enable integration tests for:

- `test_extractor.py` - ffmpeg-based audio/keyframe extraction
- `test_audio_fingerprint.py` - audio fingerprinting on real media
- `test_visual_fingerprint.py` - visual fingerprinting on real keyframes

Tests will gracefully skip if `sample.mp4` is not found.

## Recommended Sample Videos

For testing, use a short video clip (10-30 seconds):

- **Free sample:** https://www.sample-videos.com/
- **Local generation (ffmpeg):**
  ```bash
  ffmpeg -f lavfi -i testsrc=s=1920x1080:d=10 -f lavfi -i sine=f=1000:d=10 \
    -c:v libx264 -c:a aac sample.mp4
  ```

Do **not** commit `sample.mp4` to version control (excluded by `.gitignore`).
