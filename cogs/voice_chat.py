import discord
from discord.ext import commands, voice_recv
import speech_recognition as sr
from gtts import gTTS
import asyncio
import os
import io
import wave
import numpy as np
from typing import Optional, Dict, List
from datetime import datetime, timedelta
import re

class VoiceChatAudioSink(voice_recv.AudioSink):
    """AudioSink for capturing Discord voice audio."""
    
    def __init__(self, voice_chat_cog, ctx, bot):
        self.voice_chat_cog = voice_chat_cog
        self.ctx = ctx
        self.bot = bot
        self.audio_buffer = {}  # user_id -> list of audio frames
        self.last_speech_time = {}  # user_id -> timestamp
        self.processing_tasks = {}  # user_id -> asyncio.Task
        self.processing_lock = asyncio.Lock()
        
    def write(self, user, data):
        """Receive audio data from Discord voice."""
        if user and data.pcm and not user.bot:  # Ignore bot audio
            user_id = user.id
            current_time = datetime.now()
            
            if user_id not in self.audio_buffer:
                self.audio_buffer[user_id] = []
            
            self.audio_buffer[user_id].append(data.pcm)
            self.last_speech_time[user_id] = current_time
            
            # Only schedule a new task if one isn't already running for this user
            if user_id not in self.processing_tasks or self.processing_tasks[user_id].done():
                self.processing_tasks[user_id] = asyncio.run_coroutine_threadsafe(
                    self._check_and_process_audio(user_id, user),
                    self.bot.loop
                )
    
    async def _check_and_process_audio(self, user_id, user):
        """Check if user has stopped speaking and process the audio."""
        while True:
            await asyncio.sleep(0.5)  # Wait for pause
            
            current_time = datetime.now()
            if user_id not in self.last_speech_time:
                break
                
            time_since_speech = (current_time - self.last_speech_time[user_id]).total_seconds()
            
            # If it's been more than 1 second since last audio, process it
            if time_since_speech >= 1.0:
                if user_id in self.audio_buffer and self.audio_buffer[user_id]:
                    async with self.processing_lock:
                        if user_id in self.audio_buffer and self.audio_buffer[user_id]:
                            audio_frames = self.audio_buffer[user_id]
                            self.audio_buffer[user_id] = []  # Clear buffer
                            
                            # Process the audio in background
                            asyncio.create_task(
                                self.voice_chat_cog.process_discord_audio(self.ctx, audio_frames, user)
                            )
                # Exit the loop after processing
                break
    
    def wants_opus(self):
        return False
    
    def cleanup(self):
        # Cancel all processing tasks
        for task in self.processing_tasks.values():
            if not task.done():
                task.cancel()
        self.processing_tasks.clear()
        self.audio_buffer.clear()
        self.last_speech_time.clear()


class VoiceChat(commands.Cog):
    """Voice chat functionality allowing users to converse with the bot using speech."""

    def __init__(self, bot):
        self.bot = bot
        self.recognizer = sr.Recognizer()
        self.voice_clients: Dict[int, voice_recv.VoiceRecvClient] = {}
        self.audio_sinks: Dict[int, VoiceChatAudioSink] = {}
        self.conversation_contexts: Dict[int, Dict] = {}
        
        # Audio settings (Discord standard)
        self.CHANNELS = 2
        self.RATE = 48000

        # Pre-compile regex for performance
        self._think_pattern = re.compile(r'<think>.*?</think>', re.DOTALL)

        # Start cleanup task for old contexts
        self.cleanup_task = asyncio.create_task(self.cleanup_old_contexts())

    def cog_unload(self):
        """Clean up resources when cog is unloaded."""
        # Clean up audio sinks
        for sink in self.audio_sinks.values():
            sink.cleanup()

        # Disconnect from all voice channels
        for vc in self.voice_clients.values():
            asyncio.create_task(vc.disconnect())

        # Cancel cleanup task
        self.cleanup_task.cancel()

    async def cleanup_old_contexts(self):
        """Background task to clean up old conversation contexts."""
        while True:
            try:
                await asyncio.sleep(3600)  # Check every hour
                cutoff_time = datetime.now() - timedelta(hours=1)

                expired_guilds = [guild_id for guild_id, context_data in self.conversation_contexts.items()
                                if context_data["last_updated"] < cutoff_time]

                for guild_id in expired_guilds:
                    del self.conversation_contexts[guild_id]
                    print(f"Cleared voice chat context for guild {guild_id}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error in voice chat cleanup task: {e}")

    def add_message_to_context(self, guild_id: int, role: str, content: str):
        """Add a message to the conversation context for a guild."""
        now = datetime.now()
        if guild_id not in self.conversation_contexts:
            self.conversation_contexts[guild_id] = {"messages": [], "last_updated": now}

        context = self.conversation_contexts[guild_id]
        messages = context["messages"]
        messages.append({"role": role, "content": content})
        context["last_updated"] = now

        # Keep only the latest 8 messages to save context space
        if len(messages) > 8:
            messages[:] = messages[-8:]

    def get_conversation_messages(self, guild_id: int, current_prompt: str) -> List[Dict]:
        """Get the conversation messages for API call."""
        messages = [
            {"role": "system", "content": "You are a helpful assistant in a voice chat conversation. Keep responses conversational and under 200 characters to fit voice responses well. You have access to recent conversation history."}
        ]

        # Add conversation history if it exists
        if guild_id in self.conversation_contexts:
            messages.extend(self.conversation_contexts[guild_id]["messages"])

        # Add the current user message
        messages.append({"role": "user", "content": current_prompt})

        return messages

    @commands.command()
    async def test_voice(self, ctx):
        """Test command to verify the voice chat cog is loaded."""
        await ctx.reply("Voice chat cog is loaded and working! Use `!voice` to start voice chat.")
        print(f"Test voice command executed by {ctx.author}")

    @commands.command(aliases=['vc', 'voice_chat'])
    async def voice(self, ctx):
        """Start voice chat in your voice channel. The bot will listen and respond to your speech."""
        if not ctx.author.voice or not ctx.author.voice.channel:
            return await ctx.reply("You need to be in a voice channel to start voice chat!")

        voice_channel = ctx.author.voice.channel
        guild_id = ctx.guild.id

        # Check if already connected
        if guild_id in self.voice_clients and self.voice_clients[guild_id].is_connected():
            return await ctx.reply("Already connected to voice chat! Speak and I'll respond.")
        
        # Connect to voice channel with voice_recv
        try:
            vc = await voice_channel.connect(cls=voice_recv.VoiceRecvClient)
            self.voice_clients[guild_id] = vc
            
            # Create and setup audio sink
            audio_sink = VoiceChatAudioSink(self, ctx, self.bot)
            self.audio_sinks[guild_id] = audio_sink
            
            # Start listening to Discord voice
            vc.listen(audio_sink)
            
            await ctx.reply(f"🎤 Connected to {voice_channel.name} for voice chat! Speak and I'll respond.")
        except Exception as e:
            return await ctx.reply(f"Failed to connect to voice channel: {e}")

    @commands.command(aliases=['stop_vc', 'stop_voice_chat'])
    async def stop_voice(self, ctx):
        """Stop voice chat and disconnect from voice channel."""
        guild_id = ctx.guild.id

        # Clean up audio sink
        if guild_id in self.audio_sinks:
            self.audio_sinks[guild_id].cleanup()
            del self.audio_sinks[guild_id]

        # Disconnect from voice channel
        if guild_id in self.voice_clients:
            vc = self.voice_clients[guild_id]
            if vc.is_connected():
                await vc.disconnect()
            del self.voice_clients[guild_id]

        # Clear conversation context
        if guild_id in self.conversation_contexts:
            del self.conversation_contexts[guild_id]

        await ctx.reply("Voice chat stopped and disconnected.")

    async def process_discord_audio(self, ctx, audio_frames: list, user):
        """Process Discord audio frames and transcribe them."""
        guild_id = ctx.guild.id
        
        try:
            # Combine audio frames into a single byte string
            combined_audio = b''.join(audio_frames)
            
            # Convert to numpy array
            audio_array = np.frombuffer(combined_audio, dtype=np.int16)
            
            # Check if audio is too short
            if len(audio_array) < self.RATE * 0.5:  # Less than 0.5 seconds
                return
            
            # Save to temporary WAV file for speech recognition
            temp_filename = f"voice_temp_{guild_id}_{user.id}_{hash(datetime.now())}.wav"
            
            def save_wav():
                with wave.open(temp_filename, 'wb') as wav_file:
                    wav_file.setnchannels(self.CHANNELS)
                    wav_file.setsampwidth(2)  # 16-bit
                    wav_file.setframerate(self.RATE)
                    wav_file.writeframes(audio_array.tobytes())
            
            # Save WAV file
            await asyncio.get_event_loop().run_in_executor(self.bot.executor, save_wav)
            
            # Transcribe using speech recognition
            text = await self._transcribe_audio_file(temp_filename)
            
            # Clean up temp file
            try:
                await asyncio.get_event_loop().run_in_executor(
                    self.bot.executor, 
                    lambda: os.remove(temp_filename) if os.path.exists(temp_filename) else None
                )
            except Exception as e:
                print(f"Error removing temp file: {e}")
            
            if text and len(text.strip()) > 0:
                print(f"Voice input from {user.name} in {ctx.guild.name}: {text}")
                
                # Process the recognized speech
                await self.process_voice_input(ctx, text)
        
        except Exception as e:
            print(f"Error processing Discord audio: {e}")
    
    async def _transcribe_audio_file(self, audio_file: str) -> str:
        """Transcribe an audio file to text."""
        def transcribe():
            try:
                with sr.AudioFile(audio_file) as source:
                    audio = self.recognizer.record(source)
                    text = self.recognizer.recognize_google(audio)
                    return text.lower()
            except sr.UnknownValueError:
                return ""
            except sr.RequestError as e:
                print(f"Speech recognition API error: {e}")
                return ""
            except Exception as e:
                print(f"Transcription error: {e}")
                return ""
        
        return await asyncio.get_event_loop().run_in_executor(self.bot.executor, transcribe)

    async def process_voice_input(self, ctx, text: str):
        """Process recognized speech and generate AI response."""
        guild_id = ctx.guild.id

        # Add user message to context
        self.add_message_to_context(guild_id, "user", f"Voice: {text}")

        # Get AI response using Groq
        try:
            conversation_messages = self.get_conversation_messages(guild_id, text)

            # Use the bot's Groq connection pool
            groq_client = self.bot.pool.get_connection()

            completion = await asyncio.get_event_loop().run_in_executor(
                self.bot.executor,
                lambda: groq_client.chat.completions.create(
                    model="meta-llama/llama-4-maverick-17b-128e-instruct",
                    messages=conversation_messages,
                    max_tokens=150  # Shorter for voice responses
                )
            )

            ai_response = completion.choices[0].message.content

            # Clean up think tags and limit length
            ai_response = self._think_pattern.sub('', ai_response).strip()
            ai_response = ai_response[:200] + "..." if len(ai_response) > 200 else ai_response

            # Add AI response to context
            self.add_message_to_context(guild_id, "assistant", ai_response)

            # Convert response to speech
            await self.speak_response(ctx, ai_response)

        except Exception as e:
            print(f"Error processing voice input: {e}")
            error_msg = "Sorry, I had trouble understanding that."
            await self.speak_response(ctx, error_msg)

    async def speak_response(self, ctx, text: str):
        """Convert text to speech and play in voice channel."""
        guild_id = ctx.guild.id

        if guild_id not in self.voice_clients or not self.voice_clients[guild_id].is_connected():
            return

        vc = self.voice_clients[guild_id]

        try:
            # Generate TTS audio
            temp_file = f"voice_chat_{guild_id}_{hash(text)}.mp3"

            # Generate TTS in executor
            await self.bot.loop.run_in_executor(
                self.bot.executor,
                lambda: gTTS(text=text, lang='en', slow=False).save(temp_file)
            )

            # Play the audio
            def after_speaking(error):
                if error:
                    print(f"Voice playback error: {error}")
                # Clean up temp file
                async def cleanup():
                    try:
                        if os.path.exists(temp_file):
                            await self.bot.loop.run_in_executor(self.bot.executor, lambda: os.remove(temp_file))
                    except Exception as e:
                        print(f"Error removing voice temp file: {e}")
                
                asyncio.run_coroutine_threadsafe(cleanup(), self.bot.loop)

            # Stop any current playback
            if vc.is_playing():
                vc.stop()

            vc.play(discord.FFmpegPCMAudio(temp_file), after=after_speaking)

        except Exception as e:
            print(f"TTS error: {e}")
            # Try to clean up file if it exists
            try:
                await self.bot.loop.run_in_executor(self.bot.executor, os.remove, temp_file)
            except:
                pass

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Handle voice state changes to clean up disconnected clients."""
        if member == self.bot.user and before.channel and not after.channel:
            # Bot was disconnected from voice
            guild_id = member.guild.id

            # Clean up resources
            if guild_id in self.audio_sinks:
                self.audio_sinks[guild_id].cleanup()
                del self.audio_sinks[guild_id]

            if guild_id in self.voice_clients:
                del self.voice_clients[guild_id]

            if guild_id in self.conversation_contexts:
                del self.conversation_contexts[guild_id]


async def setup(bot):
    await bot.add_cog(VoiceChat(bot))
