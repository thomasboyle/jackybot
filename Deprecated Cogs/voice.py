import discord
from discord.ext import commands
import speech_recognition as sr
import yt_dlp
import asyncio
from enum import Enum

class BotState(Enum):
    IDLE = 0
    LISTENING = 1
    SEARCHING = 2
    PLAYING = 3

class VoiceBot(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.voice_clients = {}
        self.states = {}

    def is_connected(self, ctx):
        return ctx.guild.id in self.voice_clients and self.voice_clients[ctx.guild.id].is_connected()

    @commands.command()
    async def voice(self, ctx):
        if ctx.author.voice:
            channel = ctx.author.voice.channel
            if self.is_connected(ctx):
                await self.voice_clients[ctx.guild.id].move_to(channel)
                await ctx.send("Moved to your voice channel.")
            else:
                self.voice_clients[ctx.guild.id] = await channel.connect()
                await ctx.send("Connected to voice channel.")
            
            self.states[ctx.guild.id] = BotState.LISTENING
            await ctx.send("Listening for commands.")
            
            # Start listening in a separate task
            self.bot.loop.create_task(self.listen_for_commands(ctx))
        else:
            await ctx.send("You need to be in a voice channel to use this command.")

    async def listen_for_commands(self, ctx):
        r = sr.Recognizer()
        while self.is_connected(ctx):
            try:
                self.states[ctx.guild.id] = BotState.LISTENING
                with sr.Microphone() as source:
                    audio = await self.bot.loop.run_in_executor(None, r.listen, source)
                
                text = await self.bot.loop.run_in_executor(None, r.recognize_google, audio)
                if text.lower().startswith("hey jackybot"):
                    command = text[len("hey jackybot"):].strip()
                    await self.process_command(ctx, command)
            except sr.UnknownValueError:
                print("Could not understand audio")
            except sr.RequestError as e:
                print(f"Could not request results; {e}")
            
            await asyncio.sleep(0.1)  # Small delay to prevent high CPU usage

        # If we've exited the loop, we're no longer connected
        if ctx.guild.id in self.states:
            del self.states[ctx.guild.id]
        await ctx.send("Disconnected from voice channel.")

    async def process_command(self, ctx, command):
        if not self.is_connected(ctx):
            await ctx.send("I'm not connected to a voice channel. Use !voice to connect me.")
            return

        if command.lower().startswith("play"):
            query = command[5:].strip()
            self.states[ctx.guild.id] = BotState.SEARCHING
            await ctx.send(f"Searching for: {query}")
            await self.play_youtube(ctx, query)

    async def play_youtube(self, ctx, query):
        if not self.is_connected(ctx):
            await ctx.send("I'm not connected to a voice channel. Use !voice to connect me.")
            return

        voice_client = self.voice_clients[ctx.guild.id]
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = await self.bot.loop.run_in_executor(None, lambda: ydl.extract_info(f"ytsearch:{query}", download=False)['entries'][0])
                url = info['url']
            
            if voice_client.is_playing():
                voice_client.stop()

            def after_playing(error):
                if error:
                    print(f"Error in playback: {error}")
                self.bot.loop.create_task(self.after_playing(ctx))

            voice_client.play(discord.FFmpegPCMAudio(url), after=after_playing)
            self.states[ctx.guild.id] = BotState.PLAYING
            await ctx.send(f"Now playing: {info['title']}")
        except Exception as e:
            await ctx.send(f"An error occurred: {str(e)}")
            self.states[ctx.guild.id] = BotState.LISTENING

    async def after_playing(self, ctx):
        if self.is_connected(ctx):
            self.states[ctx.guild.id] = BotState.LISTENING
            await ctx.send("Finished playing. Listening for new commands.")


    @commands.command()
    async def status(self, ctx):
        if self.is_connected(ctx) and ctx.guild.id in self.states:
            state = self.states[ctx.guild.id]
            if state == BotState.IDLE:
                await ctx.send("I'm currently idle.")
            elif state == BotState.LISTENING:
                await ctx.send("I'm listening for commands. Say 'Hey Jackybot' to activate me.")
            elif state == BotState.SEARCHING:
                await ctx.send("I'm searching for a song to play.")
            elif state == BotState.PLAYING:
                await ctx.send("I'm currently playing audio.")
        else:
            await ctx.send("I'm not currently active in a voice channel.")

async def setup(bot):
    await bot.add_cog(VoiceBot(bot))