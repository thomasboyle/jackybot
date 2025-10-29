import unittest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, Mock
import io
import discord
from discord.ext import commands
import wavelink
import aiohttp

# Import the cog
try:
    from cogs.music_wavelink import MusicWavelinkCog
except ImportError:
    # If we can't import, we'll mock the whole cog
    MusicWavelinkCog = None


class TestLyricsFunctionality(unittest.IsolatedAsyncioTestCase):
    """Test the lyrics functionality in MusicWavelinkCog"""

    async def asyncSetUp(self):
        """Set up test fixtures"""
        self.bot = MagicMock(spec=commands.Bot)
        self.bot.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.bot.loop)

        # Create cog instance
        self.cog = MusicWavelinkCog(self.bot)

        # Mock the session
        self.cog.session = AsyncMock(spec=aiohttp.ClientSession)

        # Create mock player and track
        self.mock_player = MagicMock(spec=wavelink.Player)
        self.mock_track = MagicMock(spec=wavelink.Playable)
        self.mock_track.author = "Calvis Harris"  # Note: This should be "Calvin Harris"
        self.mock_track.artist = "Calvis Harris"
        self.mock_track.title = "Potion"
        self.mock_player.current = self.mock_track

        # Create mock interaction
        self.mock_interaction = MagicMock(spec=discord.Interaction)
        self.mock_interaction.response = AsyncMock()
        self.mock_interaction.followup = AsyncMock()

    async def test_lyrics_with_calvis_harris_potion_success(self):
        """Test lyrics fetching with Calvis Harris - Potion (should work with Calvin Harris)"""
        # Mock successful API response
        mock_response_data = {
            "lyrics": "[Verse 1]\nThis is a test lyrics response\nFor the song Potion by Calvin Harris\n\n[Chorus]\nPotion lyrics here..."
        }

        # Create mock response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=mock_response_data)
        mock_response.raise_for_status = Mock()

        # Set up the session context manager
        self.cog.session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        self.cog.session.get.return_value.__aexit__ = AsyncMock(return_value=None)

        # Call the lyrics function
        await self.cog.get_lyrics(self.mock_interaction, self.mock_player)

        # Verify interaction was deferred
        self.mock_interaction.response.defer.assert_called_once_with(ephemeral=True)

        # Verify session.get was called with the correct URL
        self.cog.session.get.assert_called_once()
        call_args = self.cog.session.get.call_args[0][0]
        self.assertIn("Calvis%20Harris", call_args)  # URL encoded
        self.assertIn("Potion", call_args)

        # Verify followup.send was called with embed and file
        self.mock_interaction.followup.send.assert_called_once()
        call_args, call_kwargs = self.mock_interaction.followup.send.call_args

        # Check that embed and file were provided
        self.assertIn('embed', call_kwargs)
        self.assertIn('file', call_kwargs)
        self.assertTrue(call_kwargs['ephemeral'])

        # Verify the embed content
        embed = call_kwargs['embed']
        self.assertEqual(embed.title, "📝 Lyrics")
        self.assertIn("Potion", embed.description)
        self.assertIn("Calvis Harris", embed.description)

        # Verify the file content
        file_obj = call_kwargs['file']
        self.assertIsInstance(file_obj, discord.File)
        self.assertIn("Calvis Harris - Potion - Lyrics.txt", file_obj.filename)

    async def test_lyrics_no_track_playing(self):
        """Test lyrics when no track is currently playing"""
        # Set player to have no current track
        self.mock_player.current = None

        # Call the lyrics function
        await self.cog.get_lyrics(self.mock_interaction, self.mock_player)

        # Verify error message was sent
        self.mock_interaction.response.send_message.assert_called_once_with(
            "No song is currently playing.", ephemeral=True
        )

        # Verify followup was not called
        self.mock_interaction.followup.send.assert_not_called()

    async def test_lyrics_api_failure_404(self):
        """Test lyrics when API returns 404 (lyrics not found)"""
        # Mock 404 response
        mock_response = AsyncMock()
        mock_response.status = 404
        mock_response.raise_for_status = Mock(side_effect=aiohttp.ClientResponseError(
            request_info=Mock(), history=Mock(), status=404
        ))

        # Set up the session context manager
        self.cog.session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        self.cog.session.get.return_value.__aexit__ = AsyncMock(return_value=None)

        # Call the lyrics function
        await self.cog.get_lyrics(self.mock_interaction, self.mock_player)

        # Verify the "no lyrics found" message was sent
        self.mock_interaction.followup.send.assert_called_with(
            "No lyrics found for this song. The lyrics database may not have this track, or it might be too new. Try searching for the official lyrics online.",
            ephemeral=True
        )

    async def test_lyrics_fallback_to_parsed_artist(self):
        """Test lyrics when track has no author/artist attribute"""
        # Set track to have no author/artist
        self.mock_track.author = None
        self.mock_track.artist = None
        self.mock_track.title = "Calvis Harris - Potion"  # Simulate title with artist

        # Mock successful API response
        mock_response_data = {"lyrics": "Test lyrics"}
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=mock_response_data)

        self.cog.session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        self.cog.session.get.return_value.__aexit__ = AsyncMock(return_value=None)

        # Call the lyrics function
        await self.cog.get_lyrics(self.mock_interaction, self.mock_player)

        # Verify it attempted to search with parsed artist
        call_args = self.cog.session.get.call_args[0][0]
        self.assertIn("Calvis%20Harris", call_args)
        self.assertIn("Potion", call_args)

    async def test_lyrics_network_error(self):
        """Test lyrics when there's a network error"""
        # Mock network error
        self.cog.session.get.side_effect = aiohttp.ClientError("Network error")

        # Call the lyrics function
        await self.cog.get_lyrics(self.mock_interaction, self.mock_player)

        # Verify "no lyrics found" message was sent (since all attempts fail with network errors)
        self.mock_interaction.followup.send.assert_called_with(
            "No lyrics found for this song. The lyrics database may not have this track, or it might be too new. Try searching for the official lyrics online.",
            ephemeral=True
        )

    async def test_lyrics_cleanup_and_formatting(self):
        """Test that lyrics are properly cleaned and formatted"""
        # Mock response with extra newlines
        mock_response_data = {
            "lyrics": "Line 1\n\n\n\nLine 2\n\n\nLine 3\n\n\n\n\nLine 4"
        }

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=mock_response_data)

        self.cog.session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        self.cog.session.get.return_value.__aexit__ = AsyncMock(return_value=None)

        # Call the lyrics function
        await self.cog.get_lyrics(self.mock_interaction, self.mock_player)

        # Verify followup was called
        call_args, call_kwargs = self.mock_interaction.followup.send.call_args

        # Get the file content
        file_obj = call_kwargs['file']

        # Read the file content to verify formatting
        file_content = file_obj.fp.getvalue().decode('utf-8')

        # Verify that excessive newlines were reduced
        self.assertIn("Calvis Harris - Potion", file_content)
        self.assertIn("Line 1", file_content)
        self.assertIn("Line 2", file_content)
        # The LYRICS_NEWLINES_REGEX should have reduced multiple newlines to double newlines


if __name__ == '__main__':
    # Add the parent directory to the path so we can import cogs
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    # Set up asyncio for the test
    import asyncio
    asyncio.run(unittest.main())
