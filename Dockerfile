# Multi-stage build for smaller final image
FROM python:3.10-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    portaudio19-dev \
    git \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN useradd -m -u 1000 jackybot && \
    mkdir -p /app /app/data /app/json /app/cache && \
    chown -R jackybot:jackybot /app

# Set working directory
WORKDIR /app

# Copy requirements first for better layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY --chown=jackybot:jackybot . .

# Create necessary directories with proper permissions
RUN mkdir -p assets/images assets/videos cogs codeclm data json cache && \
    chown -R jackybot:jackybot /app

# Switch to non-root user
USER jackybot

# Set environment variables for CPU inference
ENV PYTORCH_ENABLE_MPS_FALLBACK=0
ENV CUDA_VISIBLE_DEVICES=""

# Health check (optional, checks if bot process is running)
HEALTHCHECK --interval=60s --timeout=10s --start-period=120s --retries=3 \
    CMD pgrep -f "python.*bot.py" || exit 1

# Run the bot
CMD ["python", "-u", "bot.py"]

