import discord
import discord.sinks
from discord.ext import commands
import asyncio
import numpy as np
import io
import wave
from collections import deque
import logging

# Set up detailed logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('RecordCog')

class RecordSink(discord.sinks.Sink):
    def __init__(self):
        self.buffer = deque(maxlen=30 * 44100)  # 30 seconds at 44100 Hz
        logger.debug("RecordSink initialized")

    def write(self, data, user):
        try:
            logger.debug(f"Received audio data from user {user}, length: {len(data)}")
            audio_data = np.frombuffer(data, dtype=np.int16)
            for sample in audio_data:
                self.buffer.append(sample)
        except Exception as e:
            logger.error(f"Error in write: {e}")

    def cleanup(self):
        logger.debug("Cleaning up sink buffer")
        self.buffer.clear()

class RecordCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.voice_client = None
        self.recording = False
        self.sink = None
        self.sample_rate = 44100
        self.channels = 1
        self.lock = asyncio.Lock()
        logger.debug("RecordCog initialized")

    @commands.command()
    async def record(self, ctx):
        """Join voice channel and start recording"""
        logger.debug(f"Record command invoked by {ctx.author}")
        async with self.lock:
            if not ctx.author.voice:
                logger.debug("User not in voice channel")
                await ctx.send("You need to be in a voice channel to use this command!")
                return

            if self.voice_client and self.voice_client.is_connected():
                logger.debug("Already connected to a voice channel")
                await ctx.send("Already recording in a voice channel!")
                return

            try:
                voice_channel = ctx.author.voice.channel
                logger.debug(f"Attempting to connect to {voice_channel}")
                self.voice_client = await voice_channel.connect()
                logger.debug("Successfully connected to voice channel")
                
                self.sink = RecordSink()
                self.recording = True
                self.voice_client.start_recording(self.sink)  # No need for extra args here
                logger.debug("Started recording with sink")

                message = await ctx.send("Preparing to record...")
                for i in range(3, 0, -1):
                    await message.edit(content=f"Recording will start in {i}...")
                    await asyncio.sleep(1)
                await message.edit(content="Recording audio... (use !clip to get last 30s, !stop to end)")
                logger.debug("Recording started message sent")
            except Exception as e:
                logger.error(f"Error in record: {e}", exc_info=True)
                await ctx.send(f"Failed to start recording: {str(e)}")
                if self.voice_client:
                    await self.voice_client.disconnect()
                self.voice_client = None
                self.recording = False
                self.sink = None

    @commands.command()
    async def clip(self, ctx):
        """Send the last 30 seconds of recorded audio"""
        logger.debug("Clip command invoked")
        async with self.lock:
            if not self.recording or not self.voice_client or not self.sink:
                await ctx.send("Not currently recording!")
                return

            try:
                audio_data = np.array(self.sink.buffer, dtype=np.int16)
                logger.debug(f"Clip requested, buffer size: {len(audio_data)}")
                if len(audio_data) == 0:
                    await ctx.send("No audio recorded yet!")
                    return

                buffer = io.BytesIO()
                with wave.open(buffer, 'wb') as wf:
                    wf.setnchannels(self.channels)
                    wf.setsampwidth(2)
                    wf.setframerate(self.sample_rate)
                    wf.writeframes(audio_data.tobytes())

                buffer.seek(0)
                await ctx.send("Here's the last 30 seconds of audio:", 
                            file=discord.File(buffer, filename="clip.wav"))
                logger.debug("Clip sent successfully")
            except Exception as e:
                logger.error(f"Error in clip: {e}")
                await ctx.send("Error creating clip!")

    @commands.command()
    async def stop(self, ctx):
        """Stop recording and disconnect"""
        logger.debug("Stop command invoked")
        async with self.lock:
            if not self.voice_client or not self.voice_client.is_connected():
                await ctx.send("Not currently in a voice channel!")
                return

            try:
                self.recording = False
                self.voice_client.stop_recording()
                await self.voice_client.disconnect()
                self.voice_client = None
                self.sink = None
                await ctx.send("Stopped recording and disconnected.")
                logger.debug("Successfully stopped and disconnected")
            except Exception as e:
                logger.error(f"Error in stop: {e}")
                await ctx.send("Error stopping recording!")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Handle voice state changes"""
        logger.debug(f"Voice state update for {member}")
        async with self.lock:
            if not self.voice_client or not self.voice_client.is_connected():
                return

            try:
                if member == self.bot.user and after.channel is None:
                    self.recording = False
                    self.voice_client = None
                    self.sink = None
                    return

                voice_channel = self.voice_client.channel
                if len(voice_channel.members) == 1 and voice_channel.members[0] == self.bot.user:
                    self.recording = False
                    self.voice_client.stop_recording()
                    await self.voice_client.disconnect()
                    self.voice_client = None
                    self.sink = None
                    channel = member.guild.text_channels[0]
                    await channel.send("Disconnected from voice channel (alone)")
                    logger.debug("Disconnected due to being alone")
            except Exception as e:
                logger.error(f"Error in voice state update: {e}")

async def setup(bot):
    await bot.add_cog(RecordCog(bot))
    logger.debug("RecordCog added to bot")