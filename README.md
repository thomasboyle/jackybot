# jackybot

JackyBot Discord bot

### Using uv

Prereqs:
- Install `uv`: see `https://docs.astral.sh/uv/getting-started/installation/`
- Windows: install FFmpeg and make sure `ffmpeg` is on PATH (`https://ffmpeg.org/download.html`).

Setup with uv:
1. Create/activate a virtual environment (optional, uv can manage one automatically):
   - `uv venv` then `.\.venv\Scripts\activate` (PowerShell)
2. Sync dependencies from `pyproject.toml`:
   - `uv sync`
3. Run the bot:
   - `uv run python bot.py`

Notes:
- For Playwright (used by `cogs/steamos_updates.py`), install browsers once:
  - `uv run playwright install --with-deps`
- For GPU image generation cogs, install a CUDA build of PyTorch that matches your driver, e.g.:
  - `uv pip install --index-url https://download.pytorch.org/whl/cu121 torch torchvision torchaudio`
  Adjust the CUDA version as needed.
- If you prefer a plain list, see `requirements-uv.txt`.
