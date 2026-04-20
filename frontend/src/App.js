import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Moon, Sun } from 'lucide-react';
import Terminal from './components/Terminal';
import AirCommandHub from './components/AirCommandHub';
import SidePanel from './components/SidePanel';
import { sendChat, getTemplates, getSettings, getVoicePresets, updateSettings } from './api';

const genId = () => 'sess-' + Math.random().toString(36).substr(2, 12);

export default function App() {
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [sessionId] = useState(genId);
  const [templates, setTemplates] = useState([]);
  const [voicePresets, setVoicePresets] = useState([]);
  const [settings, setSettings] = useState({
    voice_preset: 'default-female', security_filter: true, sandbox_mode: true,
    theme: 'dark', assistant_name: 'Aradhya', workspace_path: '',
    model_name: 'gemma4:e4b', model_provider: 'ollama',
  });
  const [panelView, setPanelView] = useState(null);
  const [ttsEnabled, setTtsEnabled] = useState(true);
  const chatEndRef = useRef(null);

  useEffect(() => { document.documentElement.setAttribute('data-theme', settings.theme); }, [settings.theme]);

  useEffect(() => {
    getTemplates().then(d => setTemplates(d.templates || [])).catch(() => {});
    getVoicePresets().then(d => setVoicePresets(d.presets || [])).catch(() => {});
    getSettings().then(d => { const { key, ...rest } = d; setSettings(prev => ({ ...prev, ...rest })); }).catch(() => {});
  }, []);

  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);

  const speak = useCallback((text) => {
    if (!ttsEnabled || !window.speechSynthesis) return;
    window.speechSynthesis.cancel();
    const clean = text.replace(/```[\s\S]*?```/g, '').replace(/[#*`_\[\]]/g, '').replace(/\[.*?\]/g, '').trim();
    if (!clean) return;
    const u = new SpeechSynthesisUtterance(clean.slice(0, 400));
    const preset = voicePresets.find(p => p.id === settings.voice_preset);
    if (preset?.settings) {
      u.rate = preset.settings.rate || 1;
      u.pitch = preset.settings.pitch || 1;
      u.lang = preset.settings.lang || 'en-US';
      const voices = window.speechSynthesis.getVoices();
      if (preset.settings.voiceURI === 'female') {
        const v = voices.find(v => /female|zira|samantha|google.*english/i.test(v.name));
        if (v) u.voice = v;
      } else if (preset.settings.voiceURI === 'male') {
        const v = voices.find(v => /male|david|daniel|google.*uk/i.test(v.name));
        if (v) u.voice = v;
      }
    }
    window.speechSynthesis.speak(u);
  }, [ttsEnabled, voicePresets, settings.voice_preset]);

  const handleSend = useCallback(async (text) => {
    if (!text.trim() || loading) return;
    setMessages(prev => [...prev, { role: 'user', content: text, ts: Date.now() }]);
    setLoading(true);
    try {
      const data = await sendChat(text, sessionId, 'chat', settings.workspace_path);
      setMessages(prev => [...prev, { role: 'assistant', content: data.response, ts: Date.now() }]);
      speak(data.response);
    } catch (e) {
      setMessages(prev => [...prev, { role: 'system', content: `[ERR] ${e.message}`, ts: Date.now() }]);
    } finally {
      setLoading(false);
    }
  }, [loading, sessionId, settings.workspace_path, speak]);

  const handleTemplateClick = useCallback((tpl) => { handleSend(tpl.prompt); setPanelView(null); }, [handleSend]);
  const clearTerminal = useCallback(() => setMessages([]), []);
  const stopExecution = useCallback(() => { window.speechSynthesis?.cancel(); setLoading(false); }, []);

  const updateSett = useCallback((key, val) => {
    setSettings(prev => ({ ...prev, [key]: val }));
    updateSettings({ [key]: val }).catch(() => {});
  }, []);

  const toggleTheme = useCallback(() => {
    const next = settings.theme === 'dark' ? 'light' : 'dark';
    updateSett('theme', next);
  }, [settings.theme, updateSett]);

  return (
    <div className="h-screen w-full flex bg-0 tx-1 overflow-hidden" data-testid="app-container" data-theme={settings.theme}>
      <div className="flex-1 flex flex-col h-full relative">
        {/* Status Bar */}
        <div className="h-8 bg-1 border-b bdr flex items-center justify-between px-4 flex-shrink-0" data-testid="status-bar">
          <div className="flex items-center gap-3 tx-2 text-xs">
            <span className="c-green font-bold">{settings.assistant_name}</span>
            <span className="tx-3">|</span>
            <span>{settings.model_provider}:{settings.model_name}</span>
            <span className="tx-3">|</span>
            <span className={settings.sandbox_mode ? 'c-yellow' : 'c-red'}>{settings.sandbox_mode ? 'SAFE' : 'LIVE'}</span>
          </div>
          <div className="flex items-center gap-2 text-xs">
            <span className="c-green tx-3">ws: {settings.workspace_path?.split('/').pop() || '~'}</span>
            <button onClick={toggleTheme} className="tx-2 hover:tx-1 transition-colors p-1 rounded bg-h" data-testid="theme-toggle">
              {settings.theme === 'dark' ? <Sun size={14} /> : <Moon size={14} />}
            </button>
          </div>
        </div>

        <Terminal messages={messages} loading={loading} chatEndRef={chatEndRef} assistantName={settings.assistant_name} />

        {/* Unified Input */}
        <InputBar onSend={handleSend} loading={loading} assistantName={settings.assistant_name} />
      </div>

      {panelView && (
        <SidePanel view={panelView} onClose={() => setPanelView(null)} settings={settings} onSettingsChange={updateSett}
          templates={templates} setTemplates={setTemplates} onTemplateClick={handleTemplateClick}
          voicePresets={voicePresets} ttsEnabled={ttsEnabled} setTtsEnabled={setTtsEnabled} />
      )}

      <AirCommandHub onPanel={setPanelView} onClear={clearTerminal} onStop={stopExecution} onSend={handleSend}
        ttsEnabled={ttsEnabled} setTtsEnabled={setTtsEnabled} settings={settings} />
    </div>
  );
}

function InputBar({ onSend, loading, assistantName }) {
  const [text, setText] = useState('');
  const [recording, setRecording] = useState(false);
  const inputRef = useRef(null);
  const recRef = useRef(null);

  const submit = () => { if (!text.trim() || loading) return; onSend(text.trim()); setText(''); };

  const toggleMic = useCallback(() => {
    if (recording) { recRef.current?.stop(); setRecording(false); return; }
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) return;
    const rec = new SR(); rec.continuous = false; rec.interimResults = true; rec.lang = 'en-US';
    rec.onresult = (e) => setText(Array.from(e.results).map(r => r[0].transcript).join(''));
    rec.onend = () => setRecording(false);
    rec.onerror = () => setRecording(false);
    recRef.current = rec; rec.start(); setRecording(true);
  }, [recording]);

  useEffect(() => {
    const h = (e) => {
      if (e.ctrlKey && e.code === 'Space') { e.preventDefault(); toggleMic(); }
      if (e.key === 'Escape') { setText(''); }
      if (e.key === '/' && !e.ctrlKey && !e.shiftKey && document.activeElement !== inputRef.current) { e.preventDefault(); inputRef.current?.focus(); }
    };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [toggleMic]);

  return (
    <div className="border-t bdr bg-1 px-4 py-3 flex-shrink-0" data-testid="terminal-input-area">
      <div className="flex items-center gap-2">
        <span className="c-green font-bold text-sm">$</span>
        <input ref={inputRef} type="text" value={text} onChange={e => setText(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); submit(); } }}
          placeholder={`Talk to ${assistantName}... (natural language)`}
          className="flex-1 bg-transparent outline-none tx-1 placeholder:tx-3 text-sm" data-testid="chat-input" autoFocus />
        {recording && <span className="rec-pulse relative w-2 h-2 rounded-full" style={{background:'var(--red)'}} data-testid="recording-indicator" />}
        <button onClick={submit} disabled={!text.trim() || loading} className="c-green hover:c-cyan disabled:tx-3 transition-colors text-xs font-bold px-3 py-1 rounded border bdr hover:border-green-500/30" data-testid="send-button">
          {loading ? 'RUNNING...' : 'SEND'}
        </button>
      </div>
      <div className="flex gap-4 mt-1.5 text-xs tx-3">
        <span><span className="kbd">Ctrl+Space</span> voice</span>
        <span><span className="kbd">/</span> focus</span>
        <span><span className="kbd">Esc</span> clear</span>
        <span><span className="kbd">Enter</span> send</span>
      </div>
    </div>
  );
}
