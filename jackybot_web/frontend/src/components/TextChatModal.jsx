import { useState, useEffect } from 'react';
import Modal from './Modal';
import { api } from '../api/client';

function TextChatModal({ isOpen, onClose, serverId, cog }) {
  const [channels, setChannels] = useState([]);
  const [selectedChannel, setSelectedChannel] = useState('');
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [channelError, setChannelError] = useState('');

  useEffect(() => {
    if (isOpen && serverId) {
      loadChannels();
    }
  }, [isOpen, serverId]);

  useEffect(() => {
    if (cog?.required_channel && channels.length > 0) {
      const requiredChannel = channels.find(
        ch => ch.name.toLowerCase() === cog.required_channel.toLowerCase()
      );
      if (requiredChannel) {
        setSelectedChannel(requiredChannel.id);
        setChannelError('');
      } else {
        setChannelError(`Required channel "#${cog.required_channel}" not found in this server.`);
      }
    }
  }, [channels, cog]);

  const loadChannels = async () => {
    try {
      setLoading(true);
      const channelsData = await api.getServerChannels(serverId);
      setChannels(channelsData);
      if (channelsData.length > 0 && !selectedChannel) {
        setSelectedChannel(channelsData[0].id);
      }
    } catch (error) {
      console.error('Failed to load channels:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSend = async () => {
    if (!selectedChannel || !message.trim()) {
      alert('Please select a channel and enter a message.');
      return;
    }

    try {
      setSubmitting(true);
      await api.executeCogAction(serverId, cog.name, 'send_message', {
        channel_id: selectedChannel,
        message: message.trim()
      });
      alert('Message sent successfully!');
      setMessage('');
      onClose();
    } catch (error) {
      console.error('Failed to send message:', error);
      alert('Failed to send message. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  const getCommandPrefix = (cogName) => {
    const commandMap = {
      groq_chat: '@JackyBot ',
      punisher: '!punisher ',
      poll: '!poll ',
      suggestions: '!suggest ',
      trivia: '!trivia ',
      lovescore: '!love ',
      aura: '!aura ',
      help: '!help ',
      movies: '!movies ',
      highlights: '!highlight_stats',
      timezone: '!time ',
      randomnumber: '!rand ',
      freegames: '!freegames',
      zen_updates: '',
      steamos_updates: '!steamos_latest',
      server_manager: '!server_manager_status'
    };
    return commandMap[cogName] || '';
  };

  if (loading) {
    return (
      <Modal isOpen={isOpen} onClose={onClose} title={cog.display_name}>
        <div className="text-center py-8">Loading channels...</div>
      </Modal>
    );
  }

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={cog.display_name}>
      <div className="space-y-4">
        <p className="text-gray-400">{cog.description}</p>

        {cog.required_channel && (
          <div className={`p-3 rounded ${channelError ? 'bg-red-900/20 border border-red-500' : 'bg-blue-900/20 border border-blue-500'}`}>
            <p className={`text-sm ${channelError ? 'text-red-400' : 'text-blue-400'}`}>
              {channelError || `This cog requires the "#${cog.required_channel}" channel.`}
            </p>
          </div>
        )}

        <div>
          <label className="block text-sm font-medium mb-2">Select Channel</label>
          <select
            value={selectedChannel}
            onChange={(e) => setSelectedChannel(e.target.value)}
            className="w-full p-2 bg-dark-lighter rounded border border-dark-lighter focus:border-primary focus:outline-none"
            disabled={!!channelError}
          >
            {channels.map(channel => (
              <option key={channel.id} value={channel.id}>
                #{channel.name}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium mb-2">Message</label>
          <div className="mb-2 text-xs text-gray-400">
            Command prefix: <code className="bg-dark-light px-1 rounded">{getCommandPrefix(cog.name)}</code>
          </div>
          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder={`Enter your message${getCommandPrefix(cog.name) ? `. Prefix: ${getCommandPrefix(cog.name)}` : ''}`}
            className="w-full p-2 bg-dark-lighter rounded border border-dark-lighter focus:border-primary focus:outline-none resize-none h-32"
            disabled={!!channelError || submitting}
          />
        </div>

        <button
          onClick={handleSend}
          disabled={!selectedChannel || !message.trim() || !!channelError || submitting}
          className="w-full py-2 bg-primary hover:bg-primary-dark rounded disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {submitting ? 'Sending...' : 'Send Message'}
        </button>
      </div>
    </Modal>
  );
}

export default TextChatModal;
