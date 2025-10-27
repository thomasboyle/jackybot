import discord
from discord.ext import commands
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List
import json
import os


class ContextManager(commands.Cog):
    __slots__ = ('bot', 'conversation_contexts', 'cleanup_task', 'context_token_budget', 'estimated_tokens_per_message', 'groq_chat_cog')

    def __init__(self, bot):
        self.bot = bot
        self.conversation_contexts: Dict[int, Dict] = {}
        self.context_token_budget = 8000
        self.estimated_tokens_per_message = 150
        self.groq_chat_cog = None
        
        self.cleanup_task = asyncio.create_task(self.cleanup_old_contexts())

    def cog_unload(self):
        """Clean up the background task when the cog is unloaded."""
        self.cleanup_task.cancel()

    async def cog_load(self):
        """Initialize reference to GroqChat cog after both are loaded."""
        await asyncio.sleep(0.1)
        self.groq_chat_cog = self.bot.get_cog("GroqChat")

    async def cleanup_old_contexts(self):
        """Background task to clean up old conversation contexts every 60 minutes."""
        while True:
            try:
                await asyncio.sleep(3600)
                cutoff_time = datetime.now() - timedelta(hours=1)
                
                expired_guilds = [guild_id for guild_id, context_data in self.conversation_contexts.items() 
                                if context_data["last_updated"] < cutoff_time]
                
                for guild_id in expired_guilds:
                    del self.conversation_contexts[guild_id]
                    print(f"Cleared conversation context for guild {guild_id}")
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error in cleanup task: {e}")

    def estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for text using a simple heuristic.
        Based on OpenAI's approximation: ~4 characters per token for English text.
        This is a rough estimate - actual tokenization may vary.
        """
        if not text:
            return 0
        return int(len(text) / 4) + 10

    def estimate_message_tokens(self, messages: List[Dict]) -> int:
        """Estimate total tokens for a list of messages."""
        total = 0
        for msg in messages:
            total += 4
            total += self.estimate_tokens(msg.get("content", ""))
        return total

    def edit_context_for_token_budget(self, messages: List[Dict], max_tokens: int) -> List[Dict]:
        """
        Intelligent context editing inspired by Claude's approach.
        Removes stale messages while preserving conversation flow and recent context.
        
        Priority retention:
        1. Most recent messages (last 2 exchanges = 4 messages)
        2. Messages with high relevance (questions/important info)
        3. Compact older messages if needed
        """
        if not messages:
            return []
        
        current_tokens = self.estimate_message_tokens(messages)
        
        if current_tokens <= max_tokens:
            return messages
        
        min_recent_keep = min(4, len(messages))
        recent_messages = messages[-min_recent_keep:]
        older_messages = messages[:-min_recent_keep] if len(messages) > min_recent_keep else []
        
        recent_tokens = self.estimate_message_tokens(recent_messages)
        
        if recent_tokens > max_tokens:
            return messages[-2:]
        
        remaining_budget = max_tokens - recent_tokens
        
        selected_older = []
        for msg in reversed(older_messages):
            msg_tokens = self.estimate_message_tokens([msg])
            if msg_tokens <= remaining_budget:
                selected_older.insert(0, msg)
                remaining_budget -= msg_tokens
            else:
                break
        
        return selected_older + recent_messages

    def add_message_to_context(self, guild_id: int, role: str, content: str):
        """
        Add a message to the conversation context with intelligent token management.
        Implements context editing when approaching token budget.
        """
        now = datetime.now()
        if guild_id not in self.conversation_contexts:
            self.conversation_contexts[guild_id] = {
                "messages": [], 
                "last_updated": now,
                "estimated_tokens": 0
            }
        
        context = self.conversation_contexts[guild_id]
        messages = context["messages"]
        
        new_message = {"role": role, "content": content}
        messages.append(new_message)
        context["last_updated"] = now
        
        new_msg_tokens = self.estimate_message_tokens([new_message])
        context["estimated_tokens"] = context.get("estimated_tokens", 0) + new_msg_tokens
        
        max_context_tokens = int(self.context_token_budget * 0.30)
        
        if context["estimated_tokens"] > max_context_tokens:
            messages[:] = self.edit_context_for_token_budget(messages, max_context_tokens)
            context["estimated_tokens"] = self.estimate_message_tokens(messages)
            print(f"Context editing applied for guild {guild_id}. Token estimate: {context['estimated_tokens']}/{max_context_tokens}")

    async def get_conversation_messages(self, guild_id: int, current_prompt: str, message: discord.Message = None) -> List[Dict]:
        """
        Get the conversation messages for API call with token-aware context management.
        Inspired by Claude's context awareness approach.
        """
        if not self.groq_chat_cog:
            self.groq_chat_cog = self.bot.get_cog("GroqChat")
        
        system_prompt = self.groq_chat_cog.system_prompt if self.groq_chat_cog else ""
        
        system_prompt_parts = [system_prompt]
        
        if message:
            context_info = await self.groq_chat_cog.get_all_available_information(message)
            if context_info and context_info != "Additional context information is being loaded...":
                system_prompt_parts.append(f"\nAVAILABLE INFORMATION:\n{context_info}")
        
        system_prompt_parts.append("\nIMPORTANT: Keep responses concise (under 1500 characters). Use available info when relevant. Suggest commands like !freegames, !stats, !time when appropriate.")
        
        enhanced_system_prompt = "".join(system_prompt_parts)
        system_message = {"role": "system", "content": enhanced_system_prompt}
        
        system_tokens = self.estimate_message_tokens([system_message])
        
        conversation_history = []
        if guild_id in self.conversation_contexts:
            conversation_history = self.conversation_contexts[guild_id]["messages"].copy()
        
        current_message = {"role": "user", "content": current_prompt}
        current_tokens = self.estimate_message_tokens([current_message])
        
        max_history_tokens = self.context_token_budget - system_tokens - current_tokens - 512 - 200
        
        if conversation_history:
            history_tokens = self.estimate_message_tokens(conversation_history)
            if history_tokens > max_history_tokens:
                conversation_history = self.edit_context_for_token_budget(conversation_history, max_history_tokens)
                print(f"Context trimmed for API call. Estimated tokens: System={system_tokens}, History={self.estimate_message_tokens(conversation_history)}, Current={current_tokens}")
        
        messages = [system_message] + conversation_history + [current_message]
        
        total_estimated = self.estimate_message_tokens(messages)
        print(f"<budget:token_estimate>{total_estimated}/{self.context_token_budget}; {self.context_token_budget - total_estimated} estimated remaining</budget>")
        
        return messages


async def setup(bot):
    await bot.add_cog(ContextManager(bot))
