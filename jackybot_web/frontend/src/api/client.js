const API_BASE = import.meta.env.VITE_API_BASE || '/api';
const AUTH_BASE = import.meta.env.VITE_AUTH_BASE || '/auth';

export const api = {
  async getCogs() {
    const response = await fetch(`${API_BASE}/cogs`, {
      credentials: 'include'
    });
    if (!response.ok) throw new Error('Failed to fetch cogs');
    return response.json();
  },

  async getServers() {
    const response = await fetch(`${API_BASE}/servers`, {
      credentials: 'include'
    });
    if (!response.ok) throw new Error('Failed to fetch servers');
    return response.json();
  },

  async getServerSettings(serverId) {
    const response = await fetch(`${API_BASE}/servers/${serverId}/settings`, {
      credentials: 'include'
    });
    if (!response.ok) throw new Error('Failed to fetch server settings');
    return response.json();
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
    if (!response.ok) throw new Error('Failed to update settings');
    return response.json();
  },

  async getLoginUrl() {
    const response = await fetch(`${AUTH_BASE}/login`, {
      credentials: 'include'
    });
    if (!response.ok) throw new Error('Failed to get login URL');
    return response.json();
  },

  async getCurrentUser() {
    const response = await fetch(`${AUTH_BASE}/user`, {
      credentials: 'include'
    });
    if (!response.ok) throw new Error('Not authenticated');
    return response.json();
  },

  async logout() {
    const response = await fetch(`${AUTH_BASE}/logout`, {
      method: 'POST',
      credentials: 'include'
    });
    if (!response.ok) throw new Error('Failed to logout');
    return response.json();
  }
};

