import discord
import wave
import os
import asyncio
import numpy as np
from discord.ext import commands, voice_recv
from datetime import datetime

class MyAudioSink(voice_recv.AudioSink):
    def __init__(self, record_cog):
        self.record_cog = record_cog
        self.audio_frames_per_user = {}  # Dict of user_id -> list of audio frames
        self.is_recording = False

    def write(self, user, data):
        """Receive audio data from Discord voice. Called for each user's audio."""
        if self.is_recording and data.pcm:
            user_id = user.id
            if user_id not in self.audio_frames_per_user:
                self.audio_frames_per_user[user_id] = []
            self.audio_frames_per_user[user_id].append(data.pcm)

    def wants_opus(self):
        return False

    def cleanup(self):
        pass

    def start_recording(self):
        self.audio_frames_per_user = {}
        self.is_recording = True

    def stop_recording(self):
        self.is_recording = False
        return self.audio_frames_per_user

class Record(commands.Cog):
    """Audio recording functionality for voice channels."""

    def __init__(self, bot):
        self.bot = bot
        self.voice_clients = {}
        self.audio_sinks = {}
        self._lock = asyncio.Lock()  # Thread-safe access to recording state

        # Audio settings
        self.CHANNELS = 2
        self.RATE = 48000
        self.CHUNK = 960  # 20ms chunk size at 48kHz

    def _cleanup_guild(self, guild_id):
        """Clean up all resources for a guild."""
        self.voice_clients.pop(guild_id, None)
        self.audio_sinks.pop(guild_id, None)

    async def _save_wav_file(self, filename, audio_data):
        """Save audio data as WAV file."""
        def save_wav():
            with wave.open(filename, 'wb') as wav_file:
                wav_file.setnchannels(self.CHANNELS)
                wav_file.setsampwidth(2)  # 16-bit
                wav_file.setframerate(self.RATE)
                wav_file.writeframes(audio_data)

        await asyncio.get_event_loop().run_in_executor(self.bot.executor, save_wav)

    async def _convert_to_mp3(self, wav_filename, mp3_filename):
        """Convert WAV file to MP3 using ffmpeg."""
        def convert_to_mp3():
            try:
                import subprocess
                result = subprocess.run([
                    'ffmpeg', '-i', wav_filename, '-codec:a', 'libmp3lame',
                    '-qscale:a', '2', mp3_filename, '-y'
                ], capture_output=True, text=True, timeout=30)

                if result.returncode == 0:
                    os.remove(wav_filename)  # Remove WAV file if conversion successful
                    return True
                else:
                    print(f"FFmpeg conversion failed: {result.stderr}")
                    return False
            except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
                print(f"MP3 conversion error: {e}")
                return False

        return await asyncio.get_event_loop().run_in_executor(self.bot.executor, convert_to_mp3)

    def _mix_audio_tracks(self, audio_frames_per_user):
        """Mix multiple audio tracks from different users into a single track."""
        if not audio_frames_per_user:
            return b''

        # Convert each user's audio frames to numpy arrays
        user_arrays = {}
        max_length = 0

        for user_id, frames in audio_frames_per_user.items():
            if frames:  # Only process users who actually spoke
                combined_bytes = b''.join(frames)
                # Convert bytes to int16 numpy array
                audio_array = np.frombuffer(combined_bytes, dtype=np.int16)
                user_arrays[user_id] = audio_array
                max_length = max(max_length, len(audio_array))

        if not user_arrays:
            return b''

        # Pad all arrays to the same length
        padded_arrays = []
        for audio_array in user_arrays.values():
            if len(audio_array) < max_length:
                # Pad with zeros
                padded = np.pad(audio_array, (0, max_length - len(audio_array)), 'constant')
            else:
                padded = audio_array
            padded_arrays.append(padded)

        # Mix all tracks together
        mixed_audio = np.zeros(max_length, dtype=np.int32)  # Use int32 to avoid overflow during mixing
        for audio_array in padded_arrays:
            mixed_audio += audio_array.astype(np.int32)

        # Normalize and prevent clipping
        max_val = np.max(np.abs(mixed_audio))
        if max_val > 32767:  # If we exceed int16 range
            mixed_audio = mixed_audio * (32767 / max_val)

        # Convert back to int16 and then to bytes
        mixed_audio_int16 = mixed_audio.astype(np.int16)
        return mixed_audio_int16.tobytes()

    async def _send_and_cleanup_file(self, ctx, filename):
        """Send the audio file and clean it up."""
        try:
            await ctx.reply("Recording complete! 📁", file=discord.File(filename))
        except Exception as e:
            await ctx.reply(f"Recording saved but failed to upload: {e}")

        # Clean up file after sending
        def cleanup_file():
            try:
                if os.path.exists(filename):
                    os.remove(filename)
            except Exception as e:
                print(f"Error cleaning up file {filename}: {e}")

        await asyncio.get_event_loop().run_in_executor(self.bot.executor, cleanup_file)

    @commands.command()
    async def record(self, ctx):
        """Start recording audio from your voice channel."""
        if not ctx.author.voice or not ctx.author.voice.channel:
            return await ctx.reply("You need to be in a voice channel to start recording!")

        voice_channel = ctx.author.voice.channel
        guild_id = ctx.guild.id

        async with self._lock:
            # Check if already recording in this guild
            if guild_id in self.audio_sinks:
                return await ctx.reply("Already recording in this server!")

            try:
                # Connect to voice channel with voice_recv
                vc = await voice_channel.connect(cls=voice_recv.VoiceRecvClient)
                self.voice_clients[guild_id] = vc

                # Create and setup audio sink
                audio_sink = MyAudioSink(self)
                self.audio_sinks[guild_id] = audio_sink

                # Start listening
                vc.listen(audio_sink)
                audio_sink.start_recording()

                await ctx.reply(f"🎤 Started recording audio in {voice_channel.name}. Use `!stop` to stop recording.")

            except Exception as e:
                await ctx.reply(f"Failed to start recording: {e}")
                self._cleanup_guild(guild_id)

    @commands.command()
    async def stop(self, ctx):
        """Stop recording and save the audio file."""
        guild_id = ctx.guild.id

        async with self._lock:
            if guild_id not in self.audio_sinks:
                return await ctx.reply("No active recording in this server!")

            try:
                # Stop recording and get audio frames
                audio_sink = self.audio_sinks[guild_id]
                audio_frames = audio_sink.stop_recording()

                # Disconnect voice client if it exists
                if guild_id in self.voice_clients:
                    try:
                        await self.voice_clients[guild_id].disconnect()
                    except Exception as disconnect_error:
                        print(f"Warning: Error disconnecting voice client for guild {guild_id}: {disconnect_error}")

                # Clean up all resources
                self._cleanup_guild(guild_id)

                # Process the audio frames
                await self._process_audio_frames(ctx, audio_frames, guild_id)

            except Exception as e:
                print(f"Error stopping recording for guild {guild_id}: {type(e).__name__}: {e}")
                await ctx.reply("Error stopping recording. Please check the console for details.")

    async def _process_audio_frames(self, ctx, audio_frames_per_user, guild_id):
        """Process and save audio frames to a file."""
        if not audio_frames_per_user:
            return await ctx.reply("No audio was recorded.")

        # Mix audio tracks from all users
        try:
            audio_data = self._mix_audio_tracks(audio_frames_per_user)
            if not audio_data:
                return await ctx.reply("No audio was recorded.")
        except Exception as frame_error:
            print(f"Error processing audio frames for guild {guild_id}: {frame_error}")
            return await ctx.reply("Error processing recorded audio.")

        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        wav_filename = f"recording_{guild_id}_{timestamp}.wav"
        mp3_filename = f"recording_{guild_id}_{timestamp}.mp3"

        # Save as WAV first
        await ctx.reply("Processing audio...")

        try:
            await self._save_wav_file(wav_filename, audio_data)
        except Exception as save_error:
            print(f"Error saving WAV file for guild {guild_id}: {save_error}")
            return await ctx.reply("Error saving audio file.")

        # Convert to MP3 using ffmpeg (if available)
        conversion_success = await self._convert_to_mp3(wav_filename, mp3_filename)

        final_filename = mp3_filename if conversion_success else wav_filename
        await self._send_and_cleanup_file(ctx, final_filename)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Handle voice state changes to clean up disconnected clients."""
        if member == self.bot.user and before.channel and not after.channel:
            # Bot was disconnected from voice
            guild_id = member.guild.id

            # Clean up resources safely with lock
            async with self._lock:
                self._cleanup_guild(guild_id)
                print(f"Cleaned up resources for guild {guild_id}")

async def setup(bot):
    await bot.add_cog(Record(bot))
