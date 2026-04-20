import React, { useState, useEffect, useCallback } from 'react';
import { X, FolderTree, GitBranch, Settings, Zap, ChevronRight, ChevronDown, File, Folder, Plus, Trash2, RefreshCw, AlertTriangle, Moon, Sun } from 'lucide-react';
import { getWorkspaceTree, readFile, gitAction, listModels, selectModel, updateSettings, createTemplate, deleteTemplate } from '../api';

export default function SidePanel({ view, onClose, settings, onSettingsChange, templates, setTemplates, onTemplateClick, voicePresets, ttsEnabled, setTtsEnabled }) {
  const titles = { files: 'File Explorer', git: 'Git', settings: 'Settings', templates: 'Templates' };
  const icons = { files: FolderTree, git: GitBranch, settings: Settings, templates: Zap };
  const Icon = icons[view] || Settings;

  return (
    <div className="w-80 lg:w-96 h-full bg-1 border-l bdr flex flex-col flex-shrink-0 fade-up" data-testid="side-panel">
      <div className="h-10 flex items-center justify-between px-4 border-b bdr flex-shrink-0">
        <div className="flex items-center gap-2 tx-2 text-xs font-bold uppercase tracking-wider"><Icon size={14} /> {titles[view]}</div>
        <button onClick={onClose} className="tx-3 hover:tx-1 transition-colors" data-testid="close-panel"><X size={14} /></button>
      </div>
      <div className="flex-1 overflow-y-auto p-3 text-xs">
        {view === 'files' && <FilesView workspace={settings.workspace_path} />}
        {view === 'git' && <GitView workspace={settings.workspace_path} />}
        {view === 'settings' && <SettingsView settings={settings} onChange={onSettingsChange} voicePresets={voicePresets} ttsEnabled={ttsEnabled} setTtsEnabled={setTtsEnabled} />}
        {view === 'templates' && <TemplatesView templates={templates} setTemplates={setTemplates} onTemplateClick={onTemplateClick} />}
      </div>
    </div>
  );
}

// FILE EXPLORER
function FilesView({ workspace }) {
  const [tree, setTree] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);
  const [fileContent, setFileContent] = useState('');
  const [fileError, setFileError] = useState('');

  const loadTree = useCallback(async () => {
    if (!workspace) return;
    setLoading(true);
    try { const d = await getWorkspaceTree(workspace); setTree(d.tree || []); } catch {} finally { setLoading(false); }
  }, [workspace]);

  useEffect(() => { loadTree(); }, [loadTree]);

  const openFile = async (path, name) => {
    setFileError('');
    const ext = name.split('.').pop().toLowerCase();
    const textExts = ['txt','md','py','js','jsx','ts','tsx','json','yaml','yml','toml','cfg','ini','sh','bat','css','html','xml','csv','env','gitignore','log','rst','sql','r','go','rs','java','c','cpp','h','hpp','rb','php','pl','lua','vim','conf','lock'];
    const binaryExts = ['png','jpg','jpeg','gif','bmp','ico','svg','mp3','mp4','wav','avi','mov','zip','tar','gz','rar','7z','exe','dll','so','bin','dat','db','sqlite','pdf','doc','docx','xls','xlsx','ppt','pptx'];
    
    if (binaryExts.includes(ext)) {
      setFileError(`Cannot preview binary file: ${name} (.${ext}). Use an external editor.`);
      setSelectedFile(name);
      setFileContent('');
      return;
    }
    
    try {
      const d = await readFile(path);
      if (d.size > 500000) {
        setFileError(`File is large (${(d.size/1024).toFixed(0)}KB). Showing first 5000 chars.`);
      }
      setSelectedFile(d.name);
      setFileContent(d.content);
    } catch (e) {
      setFileError(`Cannot open file: ${e.message}`);
      setSelectedFile(name);
      setFileContent('');
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <span className="tx-3 text-[10px] truncate">{workspace}</span>
        <button onClick={loadTree} className="tx-3 hover:tx-2" data-testid="refresh-tree"><RefreshCw size={12} /></button>
      </div>
      {loading ? <p className="tx-3">Loading...</p> : <TreeNode items={tree} onFileClick={openFile} />}
      {selectedFile && (
        <div className="mt-3 border-t bdr pt-2" data-testid="file-preview">
          <div className="flex items-center justify-between mb-1">
            <span className="c-green font-bold text-xs">{selectedFile}</span>
            <button onClick={() => { setSelectedFile(null); setFileError(''); }} className="tx-3 hover:tx-1"><X size={12} /></button>
          </div>
          {fileError && (
            <div className="flex items-center gap-1.5 c-yellow text-xs mb-2 bg-2 p-2 rounded" data-testid="file-warning">
              <AlertTriangle size={12} /> {fileError}
            </div>
          )}
          {fileContent && <pre className="code-block p-2 text-xs tx-2 max-h-60 overflow-auto whitespace-pre-wrap">{fileContent.slice(0, 5000)}{fileContent.length > 5000 ? '\n... (truncated)' : ''}</pre>}
        </div>
      )}
    </div>
  );
}

function TreeNode({ items, onFileClick, depth = 0 }) {
  return <div style={{ paddingLeft: depth * 12 }}>{items.map((item, i) => <TreeItem key={i} item={item} onFileClick={onFileClick} depth={depth} />)}</div>;
}

function TreeItem({ item, onFileClick, depth }) {
  const [open, setOpen] = useState(depth < 1);
  if (item.type === 'dir' || item.type === 'dir_collapsed') {
    return (
      <div>
        <button onClick={() => setOpen(!open)} className="flex items-center gap-1 py-0.5 w-full text-left rounded px-1 transition-colors bg-h">
          {open ? <ChevronDown size={10} className="tx-3" /> : <ChevronRight size={10} className="tx-3" />}
          <Folder size={12} className="c-yellow" />
          <span className="tx-2">{item.name}</span>
          {item.type === 'dir_collapsed' && <span className="tx-3 text-[10px]">(skip)</span>}
        </button>
        {open && item.children && <TreeNode items={item.children} onFileClick={onFileClick} depth={depth + 1} />}
      </div>
    );
  }
  return (
    <button onClick={() => onFileClick(item.path, item.name)} className="flex items-center gap-1 py-0.5 w-full text-left rounded px-1 transition-colors bg-h" data-testid={`file-${item.name}`}>
      <span className="w-[10px]" />
      <File size={12} className="c-blue" />
      <span className="tx-2">{item.name}</span>
    </button>
  );
}

// GIT VIEW
function GitView({ workspace }) {
  const [branch, setBranch] = useState('');
  const [branches, setBranches] = useState('');
  const [status, setStatus] = useState('');
  const [log, setLog] = useState('');
  const [commitMsg, setCommitMsg] = useState('');
  const [newBranch, setNewBranch] = useState('');
  const [result, setResult] = useState(null);

  const refresh = useCallback(async () => {
    try {
      const [b, s, l, br] = await Promise.all([gitAction('current_branch',{},workspace), gitAction('status',{},workspace), gitAction('log',{},workspace), gitAction('branch',{},workspace)]);
      setBranch(b.stdout); setStatus(s.stdout || 'Clean'); setLog(l.stdout); setBranches(br.stdout);
    } catch {}
  }, [workspace]);
  useEffect(() => { refresh(); }, [refresh]);

  const doAction = async (action, args = {}) => {
    try { const r = await gitAction(action, args, workspace); setResult(r); refresh(); return r; } catch (e) { setResult({ success: false, stderr: e.message }); }
  };
  const autoMsg = async () => { const r = await doAction('auto_commit_message'); if (r?.stdout) setCommitMsg(r.stdout); };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="c-green font-bold">{branch || '...'}</span>
        <button onClick={refresh} className="tx-3 hover:tx-2" data-testid="git-refresh"><RefreshCw size={12} /></button>
      </div>
      <Sect title="Status"><pre className="text-xs tx-2 whitespace-pre-wrap">{status}</pre><div className="flex gap-2 mt-2"><Btn onClick={() => doAction('stage',{files:['.']})} label="Stage All" testId="git-stage-all" /></div></Sect>
      <Sect title="Commit">
        <div className="flex gap-1 mb-1"><input value={commitMsg} onChange={e=>setCommitMsg(e.target.value)} placeholder="Commit message..." className="flex-1 bg-transparent border bdr rounded px-2 py-1 text-xs tx-1 outline-none" data-testid="git-commit-input" /><Btn onClick={autoMsg} label="AI" testId="git-auto-msg" /></div>
        <Btn onClick={() => doAction('commit',{message:commitMsg})} label="Commit" testId="git-commit-button" disabled={!commitMsg} />
      </Sect>
      <Sect title="Push"><Btn onClick={() => doAction('push',{branch})} label={`Push origin/${branch}`} testId="git-push-button" /></Sect>
      <Sect title="Branches"><pre className="text-xs tx-3 whitespace-pre-wrap mb-2">{branches}</pre>
        <div className="flex gap-1"><input value={newBranch} onChange={e=>setNewBranch(e.target.value)} placeholder="New branch..." className="flex-1 bg-transparent border bdr rounded px-2 py-1 text-xs tx-1 outline-none" data-testid="git-new-branch-input" /><Btn onClick={()=>{doAction('create_branch',{branch:newBranch});setNewBranch('');}} label="Create" testId="git-create-branch" disabled={!newBranch} /></div>
      </Sect>
      <Sect title="Log"><pre className="text-xs tx-3 whitespace-pre-wrap">{log}</pre></Sect>
      {result && <div className={`text-xs p-2 rounded border ${result.success ? 'c-green' : 'c-red'}`} style={{borderColor:result.success?'var(--green)':'var(--red)'}} data-testid="git-result">{result.stdout || result.stderr || (result.success ? 'Done' : 'Failed')}</div>}
    </div>
  );
}

// SETTINGS VIEW
function SettingsView({ settings, onChange, voicePresets, ttsEnabled, setTtsEnabled }) {
  const [models, setModels] = useState({ local_models: [], cloud_models: [] });
  const [name, setName] = useState(settings.assistant_name || 'Aradhya');
  const [wsPath, setWsPath] = useState(settings.workspace_path || '');

  useEffect(() => { listModels().then(setModels).catch(() => {}); }, []);

  const save = async (key, val) => {
    onChange(key, val);
    try { await updateSettings({ [key]: val }); } catch {}
  };

  return (
    <div className="space-y-4">
      <Sect title="Appearance">
        <div className="flex gap-2 items-center">
          <span className="tx-2 text-xs">Theme:</span>
          <button onClick={() => save('theme', 'dark')} className={`p-1.5 rounded transition-colors ${settings.theme==='dark'?'bg-2 tx-1':'tx-3 bg-h'}`} data-testid="theme-dark"><Moon size={14} /></button>
          <button onClick={() => save('theme', 'light')} className={`p-1.5 rounded transition-colors ${settings.theme==='light'?'bg-2 tx-1':'tx-3 bg-h'}`} data-testid="theme-light"><Sun size={14} /></button>
        </div>
      </Sect>

      <Sect title="Assistant Name">
        <div className="flex gap-1">
          <input value={name} onChange={e=>setName(e.target.value)} className="flex-1 bg-transparent border bdr rounded px-2 py-1 text-xs tx-1 outline-none" data-testid="assistant-name-input" />
          <Btn onClick={() => save('assistant_name', name)} label="Save" testId="save-name" />
        </div>
      </Sect>

      <Sect title="Model (Local First)">
        <div className="space-y-1">
          {models.local_models?.length > 0 ? (
            <>
              <p className="tx-3 text-[10px] font-bold mb-1">LOCAL (OLLAMA):</p>
              {models.local_models.map(m => (
                <button key={m.name} onClick={() => { save('model_name', m.name); save('model_provider', 'ollama'); selectModel(m.name, 'ollama').catch(()=>{}); }}
                  className={`block w-full text-left px-2 py-1 rounded text-xs transition-colors bg-h ${settings.model_name===m.name?'c-green bg-2':'tx-2'}`} data-testid={`model-${m.name}`}>
                  {m.name} <span className="tx-3">(local)</span>
                </button>
              ))}
            </>
          ) : (
            <div className="bg-2 rounded p-2 text-xs">
              <p className="c-yellow mb-1">No local Ollama models detected.</p>
              <p className="tx-3">Install Ollama and pull a model:</p>
              <code className="c-cyan text-[10px]">ollama pull gemma4:e4b</code>
            </div>
          )}
          <p className="tx-3 text-[10px] font-bold mt-2 mb-1">CLOUD (OPTIONAL):</p>
          {models.cloud_models?.map(m => (
            <button key={m.name} onClick={() => { save('model_name', m.name); save('model_provider', m.provider); selectModel(m.name, m.provider).catch(()=>{}); }}
              className={`block w-full text-left px-2 py-1 rounded text-xs transition-colors bg-h ${settings.model_name===m.name?'c-blue bg-2':'tx-2'}`} data-testid={`model-${m.name}`}>
              {m.provider}/{m.name}
            </button>
          ))}
        </div>
      </Sect>

      <Sect title="Workspace">
        <div className="flex gap-1">
          <input value={wsPath} onChange={e=>setWsPath(e.target.value)} className="flex-1 bg-transparent border bdr rounded px-2 py-1 text-xs tx-1 outline-none" data-testid="workspace-path-input" />
          <Btn onClick={() => save('workspace_path', wsPath)} label="Set" testId="save-workspace" />
        </div>
      </Sect>

      <Sect title="Security">
        <Toggle label="Sandbox Mode" desc="Block shell/file writes until disabled" checked={settings.sandbox_mode} onChange={() => save('sandbox_mode', !settings.sandbox_mode)} testId="sandbox-toggle" />
        <Toggle label="Security Filter" desc="Filter malicious web content" checked={settings.security_filter} onChange={() => save('security_filter', !settings.security_filter)} testId="security-toggle" />
      </Sect>

      <Sect title="Voice & TTS">
        <Toggle label="Speak Responses" desc="Voice replies from assistant" checked={ttsEnabled} onChange={() => setTtsEnabled(!ttsEnabled)} testId="tts-toggle" />
        <div className="space-y-1 mt-2">
          {voicePresets.map(p => (
            <button key={p.id} onClick={() => save('voice_preset', p.id)}
              className={`block w-full text-left px-2 py-1.5 rounded text-xs transition-colors bg-h ${settings.voice_preset===p.id?'c-cyan bg-2':'tx-2'}`} data-testid={`voice-${p.id}`}>
              {p.name} <span className="tx-3">- {p.description}</span>
            </button>
          ))}
        </div>
      </Sect>

      <Sect title="Model Optimization">
        <p className="tx-3 text-xs">Use quantized (Q4/Q5) Ollama models for faster local inference. Pull with:</p>
        <code className="c-cyan text-[10px]">ollama pull model_name:q4_0</code>
      </Sect>
    </div>
  );
}

// TEMPLATES VIEW
function TemplatesView({ templates, setTemplates, onTemplateClick }) {
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ title: '', description: '', prompt: '', platform: 'linux', level: 'user' });

  const handleCreate = async () => {
    if (!form.title || !form.prompt) return;
    try { const t = await createTemplate(form); setTemplates(prev => [...prev, t]); setForm({ title:'',description:'',prompt:'',platform:'linux',level:'user' }); setShowForm(false); } catch {}
  };
  const handleDelete = async (id) => { try { await deleteTemplate(id); setTemplates(prev => prev.filter(t => t.id !== id)); } catch {} };

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between mb-2">
        <span className="tx-2 font-bold text-xs">{templates.length} templates</span>
        <button onClick={() => setShowForm(!showForm)} className="c-green hover:c-cyan text-xs flex items-center gap-1" data-testid="add-template-button"><Plus size={12} /> New</button>
      </div>
      {showForm && (
        <div className="border bdr rounded p-2 space-y-2 mb-3" data-testid="template-form">
          <input value={form.title} onChange={e=>setForm(p=>({...p,title:e.target.value}))} placeholder="Title" className="w-full bg-transparent border bdr rounded px-2 py-1 text-xs tx-1 outline-none" data-testid="template-title-input" />
          <input value={form.description} onChange={e=>setForm(p=>({...p,description:e.target.value}))} placeholder="Description" className="w-full bg-transparent border bdr rounded px-2 py-1 text-xs tx-1 outline-none" data-testid="template-desc-input" />
          <textarea value={form.prompt} onChange={e=>setForm(p=>({...p,prompt:e.target.value}))} placeholder="Prompt" className="w-full bg-transparent border bdr rounded px-2 py-1 text-xs tx-1 outline-none h-16 resize-none" data-testid="template-prompt-input" />
          <div className="flex gap-2">
            <select value={form.platform} onChange={e=>setForm(p=>({...p,platform:e.target.value}))} className="bg-1 border bdr rounded px-2 py-1 text-xs tx-2" data-testid="template-platform-select"><option value="linux">Linux</option><option value="windows">Windows</option><option value="macos">macOS</option></select>
            <Btn onClick={handleCreate} label="Create" testId="create-template-submit" />
          </div>
        </div>
      )}
      {templates.map(tpl => (
        <div key={tpl.id} className="border bdr rounded p-2 transition-colors group bg-h" data-testid={`template-${tpl.id}`}>
          <div className="flex items-start justify-between">
            <button onClick={() => onTemplateClick(tpl)} className="text-left flex-1">
              <div className="tx-1 text-xs font-bold">{tpl.title}</div>
              <div className="tx-3 text-[10px] mt-0.5">{tpl.description}</div>
              {tpl.level === 'admin' && <span className="text-[9px] c-red border rounded px-1 mt-1 inline-block" style={{borderColor:'var(--red)'}}>ADMIN</span>}
            </button>
            {!tpl.builtin && <button onClick={() => handleDelete(tpl.id)} className="tx-3 hover:c-red opacity-0 group-hover:opacity-100 transition-opacity" data-testid={`delete-template-${tpl.id}`}><Trash2 size={12} /></button>}
          </div>
        </div>
      ))}
    </div>
  );
}

// SHARED
function Sect({ title, children }) { return <div className="mb-3"><h3 className="tx-3 text-[10px] font-bold uppercase tracking-wider mb-1.5">{title}</h3>{children}</div>; }
function Btn({ onClick, label, testId, disabled }) { return <button onClick={onClick} disabled={disabled} className="px-2 py-1 rounded text-xs border bdr tx-2 hover:tx-1 transition-colors disabled:opacity-30 bg-h" data-testid={testId}>{label}</button>; }
function Toggle({ label, desc, checked, onChange, testId }) {
  return (
    <div className="flex items-start justify-between gap-2 py-1">
      <div><div className="text-xs tx-1">{label}</div>{desc && <div className="text-[10px] tx-3">{desc}</div>}</div>
      <button onClick={onChange} className={`relative w-8 h-4 rounded-full transition-colors flex-shrink-0 ${checked?'':'bg-3'}`} style={{background:checked?'var(--green)':undefined}} data-testid={testId}>
        <span className={`absolute top-0.5 left-0.5 w-3 h-3 rounded-full bg-white transition-transform ${checked?'translate-x-4':''}`} style={{boxShadow:'0 1px 3px rgba(0,0,0,0.3)'}} />
      </button>
    </div>
  );
}
