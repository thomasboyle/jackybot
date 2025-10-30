import { useState, useEffect } from 'react';
import Modal from './Modal';
import { api } from '../api/client';

function RoleManagementModal({ isOpen, onClose, serverId, cog }) {
  const [roles, setRoles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('auto-roles');
  const [selectedRoles, setSelectedRoles] = useState([]);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (isOpen && serverId) {
      loadRoles();
    }
  }, [isOpen, serverId]);

  const loadRoles = async () => {
    try {
      setLoading(true);
      const rolesData = await api.getServerRoles(serverId);
      const manageableRoles = rolesData
        .filter(role => role.name !== '@everyone' && !role.managed)
        .sort((a, b) => b.position - a.position)
        .slice(0, 25);
      setRoles(manageableRoles);
    } catch (error) {
      console.error('Failed to load roles:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleRoleToggle = (roleId) => {
    setSelectedRoles(prev => 
      prev.includes(roleId)
        ? prev.filter(id => id !== roleId)
        : [...prev, roleId]
    );
  };

  const handleSaveAutoRoles = async () => {
    try {
      setSubmitting(true);
      await api.executeCogAction(serverId, cog.name, 'update_auto_roles', {
        role_ids: selectedRoles
      });
      alert('Auto-roles updated successfully! Note: This requires bot integration to take effect.');
      onClose();
    } catch (error) {
      console.error('Failed to update auto-roles:', error);
      alert('Failed to update auto-roles. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  const handleBulkAdd = async (roleId) => {
    try {
      setSubmitting(true);
      await api.executeCogAction(serverId, cog.name, 'bulk_add_role', {
        role_id: roleId
      });
      alert('Bulk role addition initiated! Note: This requires bot integration to take effect.');
      onClose();
    } catch (error) {
      console.error('Failed to add role:', error);
      alert('Failed to add role. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  const handleBulkRemove = async (roleId) => {
    try {
      setSubmitting(true);
      await api.executeCogAction(serverId, cog.name, 'bulk_remove_role', {
        role_id: roleId
      });
      alert('Bulk role removal initiated! Note: This requires bot integration to take effect.');
      onClose();
    } catch (error) {
      console.error('Failed to remove role:', error);
      alert('Failed to remove role. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <Modal isOpen={isOpen} onClose={onClose} title={cog.display_name}>
        <div className="text-center py-8">Loading roles...</div>
      </Modal>
    );
  }

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={cog.display_name}>
      <div className="space-y-4">
        <div className="flex gap-2 border-b border-dark-lighter pb-2">
          <button
            onClick={() => setActiveTab('auto-roles')}
            className={`px-4 py-2 rounded ${
              activeTab === 'auto-roles'
                ? 'bg-primary text-white'
                : 'bg-dark-lighter text-gray-400 hover:text-white'
            }`}
          >
            Auto-Roles
          </button>
          <button
            onClick={() => setActiveTab('bulk')}
            className={`px-4 py-2 rounded ${
              activeTab === 'bulk'
                ? 'bg-primary text-white'
                : 'bg-dark-lighter text-gray-400 hover:text-white'
            }`}
          >
            Bulk Operations
          </button>
        </div>

        {activeTab === 'auto-roles' && (
          <div className="space-y-4">
            <p className="text-gray-400">
              Select roles that will automatically be given to new members when they join the server.
            </p>
            <div className="max-h-96 overflow-y-auto space-y-2">
              {roles.map(role => (
                <label
                  key={role.id}
                  className="flex items-center gap-3 p-3 rounded bg-dark-lighter hover:bg-dark-light transition-colors cursor-pointer"
                >
                  <input
                    type="checkbox"
                    checked={selectedRoles.includes(role.id)}
                    onChange={() => handleRoleToggle(role.id)}
                    className="w-4 h-4"
                  />
                  <div className="flex-1">
                    <div className="font-medium">{role.name}</div>
                    <div className="text-sm text-gray-400">
                      Position: {role.position}
                    </div>
                  </div>
                </label>
              ))}
            </div>
            <button
              onClick={handleSaveAutoRoles}
              disabled={submitting}
              className="w-full py-2 bg-primary hover:bg-primary-dark rounded disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {submitting ? 'Saving...' : 'Save Auto-Roles'}
            </button>
          </div>
        )}

        {activeTab === 'bulk' && (
          <div className="space-y-4">
            <p className="text-gray-400">
              Add or remove a role from all members in the server.
            </p>
            <div className="max-h-96 overflow-y-auto space-y-2">
              {roles.map(role => (
                <div
                  key={role.id}
                  className="flex items-center justify-between p-3 rounded bg-dark-lighter"
                >
                  <div>
                    <div className="font-medium">{role.name}</div>
                    <div className="text-sm text-gray-400">
                      Position: {role.position}
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={() => handleBulkAdd(role.id)}
                      disabled={submitting}
                      className="px-4 py-1 bg-green-600 hover:bg-green-700 rounded disabled:opacity-50"
                    >
                      Add to All
                    </button>
                    <button
                      onClick={() => handleBulkRemove(role.id)}
                      disabled={submitting}
                      className="px-4 py-1 bg-red-600 hover:bg-red-700 rounded disabled:opacity-50"
                    >
                      Remove from All
                    </button>
                  </div>
                </div>
              ))}
            </div>
            <p className="text-xs text-gray-500">
              Note: Bulk operations require bot integration to take effect.
            </p>
          </div>
        )}
      </div>
    </Modal>
  );
}

export default RoleManagementModal;
