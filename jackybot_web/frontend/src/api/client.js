const API_BASE = import.meta.env.VITE_API_BASE || '/api';
const AUTH_BASE = import.meta.env.VITE_AUTH_BASE || '/auth';

async function handleResponse(response) {
  if (!response.ok) {
    let errorMessage = `Request failed with status ${response.status}`;
    try {
      const errorData = await response.json();
      if (errorData.error) {
        errorMessage = errorData.error;
      }
    } catch (e) {
      // If response is not JSON, use default message
    }
    const error = new Error(errorMessage);
    error.status = response.status;
    throw error;
  }
  return response.json();
}

export const api = {
  async getCogs() {
    const response = await fetch(`${API_BASE}/cogs`, {
      credentials: 'include'
    });
    return handleResponse(response);
  },

  async getServers() {
    const response = await fetch(`${API_BASE}/servers`, {
      credentials: 'include'
    });
    return handleResponse(response);
  },

  async getServerSettings(serverId) {
    const response = await fetch(`${API_BASE}/servers/${serverId}/settings`, {
      credentials: 'include'
    });
    return handleResponse(response);
  },

  async updateServerSettings(serverId, cogName, enabled) {
    const response = await fetch(`${API_BASE}/servers/${serverId}/settings`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      credentials: 'include',
      body: JSON.stringify({ cog_name: cogName, enabled })
    });
    return handleResponse(response);
  },

  async getLoginUrl() {
    const response = await fetch(`${AUTH_BASE}/login`, {
      credentials: 'include'
    });
    return handleResponse(response);
  },

  async getCurrentUser() {
    const response = await fetch(`${AUTH_BASE}/user`, {
      credentials: 'include'
    });
    return handleResponse(response);
  },

  async logout() {
    const response = await fetch(`${AUTH_BASE}/logout`, {
      method: 'POST',
      credentials: 'include'
    });
    return handleResponse(response);
  },

  async checkChannelExists(serverId, channelName) {
    const response = await fetch(`${API_BASE}/servers/${serverId}/channels/${channelName}`, {
      credentials: 'include'
    });
    return handleResponse(response);
  },

  async getServerChannels(serverId) {
    const response = await fetch(`${API_BASE}/servers/${serverId}/channels`, {
      credentials: 'include'
    });
    return handleResponse(response);
  },

  async getHighlightsChannel(serverId) {
    const response = await fetch(`${API_BASE}/servers/${serverId}/cogs/highlights/channel`, {
      credentials: 'include'
    });
    return handleResponse(response);
  },

  async setHighlightsChannel(serverId, channelName) {
    const response = await fetch(`${API_BASE}/servers/${serverId}/cogs/highlights/channel`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      credentials: 'include',
      body: JSON.stringify({ channel_name: channelName })
    });
    return handleResponse(response);
  }
};

