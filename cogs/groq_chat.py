import discord
from discord.ext import commands
import groq
import os
from typing import Optional, Dict, List
import re
import asyncio
from datetime import datetime, timedelta

class GroqChat(commands.Cog):
    __slots__ = ('bot', 'groq_client', 'model', 'conversation_contexts', 'cleanup_task', '_bot_id', '_bot_mentions', '_think_pattern')
    
    def __init__(self, bot):
        self.bot = bot
        self.groq_api_key = os.environ.get("GROQ_API_KEY")
        if not self.groq_api_key:
            print("WARNING: GROQ_API_KEY not set. Groq integration will not work.")
            self.groq_client = None
        else:
            self.groq_client = groq.Client(api_key=self.groq_api_key)
        # Default model to use - hardcoded
        self.model = "meta-llama/llama-4-maverick-17b-128e-instruct"
        
        # Pre-compile regex and cache bot mentions for performance
        self._bot_id = "1128674354696310824"
        self._bot_mentions = (f"<@{self._bot_id}>", f"<@!{self._bot_id}>")
        self._think_pattern = re.compile(r'<think>.*?</think>', re.DOTALL)
        
        # Conversation context storage: guild_id -> {"messages": [...], "last_updated": datetime}
        self.conversation_contexts: Dict[int, Dict] = {}
        
        # Start the context cleanup task
        self.cleanup_task = asyncio.create_task(self.cleanup_old_contexts())
        
    def cog_unload(self):
        """Clean up the background task when the cog is unloaded."""
        self.cleanup_task.cancel()
    
    async def cleanup_old_contexts(self):
        """Background task to clean up old conversation contexts every 60 minutes."""
        while True:
            try:
                await asyncio.sleep(3600)  # Wait 60 minutes
                cutoff_time = datetime.now() - timedelta(hours=1)
                
                # Use list comprehension for better performance
                expired_guilds = [guild_id for guild_id, context_data in self.conversation_contexts.items() 
                                if context_data["last_updated"] < cutoff_time]
                
                for guild_id in expired_guilds:
                    del self.conversation_contexts[guild_id]
                    print(f"Cleared conversation context for guild {guild_id}")
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error in cleanup task: {e}")
    
    def add_message_to_context(self, guild_id: int, role: str, content: str):
        """Add a message to the conversation context for a guild."""
        now = datetime.now()
        if guild_id not in self.conversation_contexts:
            self.conversation_contexts[guild_id] = {"messages": [], "last_updated": now}
        
        context = self.conversation_contexts[guild_id]
        messages = context["messages"]
        messages.append({"role": role, "content": content})
        context["last_updated"] = now
        
        # Keep only the latest 10 messages using slice assignment for efficiency
        if len(messages) > 10:
            messages[:] = messages[-10:]
    
    def get_conversation_messages(self, guild_id: int, current_prompt: str) -> List[Dict]:
        """Get the conversation messages for API call."""
        messages = [
            {"role": "system", "content": "You are a helpful assistant in a Discord chat. Keep your total response under 2000 characters. You have access to recent conversation history to provide contextual responses."}
        ]
        
        # Add conversation history if it exists
        if guild_id in self.conversation_contexts:
            messages.extend(self.conversation_contexts[guild_id]["messages"])
        
        # Add the current user message
        messages.append({"role": "user", "content": current_prompt})
        
        return messages
        
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Don't respond to messages from bots to prevent loops
        if message.author.bot or not message.guild:
            return
            
        guild_id = message.guild.id
        content = message.content
        
        # Check if the bot is mentioned in the message using cached mentions
        if not any(mention in content for mention in self._bot_mentions):
            # For non-mention messages, still add them to context for better conversation flow
            # Only add if the message is reasonably short to avoid context bloat
            if len(content) <= 500:
                self.add_message_to_context(guild_id, "user", f"{message.author.display_name}: {content}")
            return
        
        # Check if this is a reply to another message
        if message.reference and message.reference.message_id:
            try:
                # Fetch the original message being replied to
                original_message = await message.channel.fetch_message(message.reference.message_id)
                
                # Remove the mention from the reply content using replace with cached mentions
                user_request = content
                for mention in self._bot_mentions:
                    user_request = user_request.replace(mention, "", 1)
                user_request = user_request.strip()
                
                # If user request is empty after removing mention, provide a helpful message
                if not user_request:
                    await message.reply("Hello! Please provide instructions along with the mention for me to process the replied message.")
                    return
                
                # Combine original message and user request as the prompt
                prompt = f"Original message from {original_message.author.display_name}: \"{original_message.content}\"\n\nUser request: {user_request}"
                
            except discord.NotFound:
                await message.reply("Sorry, I couldn't find the original message you're replying to.")
                return
            except discord.HTTPException as e:
                await message.reply(f"Sorry, I couldn't fetch the original message: {str(e)}")
                return
        else:
            # Regular mention without reply - remove mentions using cached values
            prompt = content
            for mention in self._bot_mentions:
                prompt = prompt.replace(mention, "", 1)
            prompt = prompt.strip()
            
            # If prompt is empty after removing mention, provide a helpful message
            if not prompt:
                await message.reply("Hello! Please provide a message along with the mention for me to respond.")
                return
        
        # Check if Groq client is initialized
        if not self.groq_client:
            await message.reply("Sorry, the Groq API key is not configured.")
            return
            
        # Show typing indicator while processing
        async with message.channel.typing():
            try:
                # Get conversation messages including context
                conversation_messages = self.get_conversation_messages(guild_id, prompt)
                
                # Call Groq API with conversation context
                response = await self.get_groq_response(conversation_messages)
                
                # Process <think> tags and ensure response is under 2000 characters
                formatted_response = self.format_response(response)
                
                # Add user message and bot response to context
                self.add_message_to_context(guild_id, "user", prompt)
                self.add_message_to_context(guild_id, "assistant", formatted_response)
                
                # Send the response
                await message.reply(formatted_response)
            except Exception as e:
                await message.reply(f"Sorry, I encountered an error: {str(e)}")
    
    def format_response(self, response: str) -> str:
        """Format the response with special handling for <think> tags and enforce length limit."""
        # Remove <think> sections using pre-compiled regex
        formatted = self._think_pattern.sub('', response).strip()
        
        # Ensure the response is under 2000 characters using slice assignment
        return formatted[:1997] + "..." if len(formatted) > 2000 else formatted
    
    async def get_groq_response(self, messages: List[Dict]) -> str:
        """Get a response from Groq API."""
        try:
            completion = self.groq_client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=1024
            )
            return completion.choices[0].message.content
        except Exception as e:
            print(f"Error calling Groq API: {str(e)}")
            raise

async def setup(bot):
    await bot.add_cog(GroqChat(bot)) 