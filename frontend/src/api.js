const API = process.env.REACT_APP_BACKEND_URL;

const f = async (url, opts = {}) => {
  const res = await fetch(`${API}${url}`, { headers: { 'Content-Type': 'application/json' }, ...opts });
  if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || 'Request failed'); }
  return res.json();
};

export const health = () => f('/api/health');
export const sendChat = (message, session_id, mode = 'chat', workspace_path) => f('/api/chat', { method: 'POST', body: JSON.stringify({ message, session_id, mode, workspace_path }) });
export const getChatHistory = (sid) => f(`/api/chat/history?session_id=${sid}`);
export const generateCommand = (description, platform, level) => f('/api/command/generate', { method: 'POST', body: JSON.stringify({ description, platform, level }) });
export const getTemplates = () => f('/api/command/templates');
export const createTemplate = (data) => f('/api/command/templates', { method: 'POST', body: JSON.stringify(data) });
export const deleteTemplate = (id) => f(`/api/command/templates/${id}`, { method: 'DELETE' });
export const webSearch = (query, security_filter) => f('/api/search', { method: 'POST', body: JSON.stringify({ query, security_filter }) });
export const getVoicePresets = () => f('/api/voice/presets');
export const getSettings = () => f('/api/settings');
export const updateSettings = (data) => f('/api/settings', { method: 'PUT', body: JSON.stringify(data) });
export const getWorkspaceTree = (path) => f('/api/workspace/tree', { method: 'POST', body: JSON.stringify({ path }) });
export const readFile = (path) => f('/api/workspace/read', { method: 'POST', body: JSON.stringify({ path }) });
export const writeFile = (path, content) => f('/api/workspace/write', { method: 'POST', body: JSON.stringify({ path, content }) });
export const getDiff = (path, new_content) => f('/api/workspace/diff', { method: 'POST', body: JSON.stringify({ path, new_content }) });
export const execShell = (command, cwd) => f('/api/shell/execute', { method: 'POST', body: JSON.stringify({ command, cwd }) });
export const gitAction = (action, args, cwd) => f('/api/git', { method: 'POST', body: JSON.stringify({ action, args, cwd }) });
export const listModels = () => f('/api/models/list');
export const selectModel = (model_name, provider) => f('/api/models/select', { method: 'POST', body: JSON.stringify({ model_name, provider }) });
