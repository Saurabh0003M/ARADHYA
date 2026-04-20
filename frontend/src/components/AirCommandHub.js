import React, { useState, useRef, useCallback } from 'react';
import { Mic, MicOff, Monitor, Trash2, Square, FolderTree, GitBranch, Settings, Zap, Volume2, VolumeX, Globe, Shield } from 'lucide-react';

export default function AirCommandHub({ onPanel, onClear, onStop, onSend, ttsEnabled, setTtsEnabled, settings }) {
  const [expanded, setExpanded] = useState(false);
  const [recording, setRecording] = useState(false);
  const [micActive, setMicActive] = useState(false);
  const [internetActive, setInternetActive] = useState(false);
  const recRef = useRef(null);
  const hideTimer = useRef(null);

  const startHide = () => { hideTimer.current = setTimeout(() => setExpanded(false), 400); };
  const cancelHide = () => { clearTimeout(hideTimer.current); };

  const toggleMic = useCallback(() => {
    if (recording) { recRef.current?.stop(); setRecording(false); setMicActive(false); return; }
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) return;
    const rec = new SR(); rec.continuous = false; rec.interimResults = false; rec.lang = 'en-US';
    rec.onresult = (e) => { const t = e.results[0][0].transcript; if (t) onSend(t); };
    rec.onend = () => { setRecording(false); setMicActive(false); };
    rec.onerror = () => { setRecording(false); setMicActive(false); };
    recRef.current = rec; rec.start(); setRecording(true); setMicActive(true);
  }, [recording, onSend]);

  const quickActions = [
    { icon: recording ? MicOff : Mic, label: 'Mic', action: toggleMic, active: micActive, color: recording ? 'c-red' : 'c-green', testId: 'mic-toggle-button' },
    { icon: Monitor, label: 'Screen', action: () => {}, active: false, color: 'c-blue', testId: 'screen-toggle-button' },
    { icon: Globe, label: 'Internet', action: () => setInternetActive(!internetActive), active: internetActive, color: internetActive ? 'c-cyan' : 'tx-3', testId: 'internet-toggle-button' },
    { icon: Shield, label: 'Interact', action: () => {}, active: !settings.sandbox_mode, color: settings.sandbox_mode ? 'tx-3' : 'c-orange', testId: 'interact-toggle-button' },
    { icon: ttsEnabled ? Volume2 : VolumeX, label: 'Voice', action: () => setTtsEnabled(!ttsEnabled), active: ttsEnabled, color: ttsEnabled ? 'c-purple' : 'tx-3', testId: 'tts-toggle-button' },
  ];

  const panelActions = [
    { icon: FolderTree, label: 'Files', action: () => { onPanel('files'); setExpanded(false); }, color: 'c-purple', testId: 'files-panel-button' },
    { icon: GitBranch, label: 'Git', action: () => { onPanel('git'); setExpanded(false); }, color: 'c-orange', testId: 'git-panel-button' },
    { icon: Zap, label: 'Templates', action: () => { onPanel('templates'); setExpanded(false); }, color: 'c-yellow', testId: 'templates-panel-button' },
    { icon: Settings, label: 'Settings', action: () => { onPanel('settings'); setExpanded(false); }, color: 'c-blue', testId: 'settings-panel-button' },
  ];

  const utilActions = [
    { icon: Trash2, label: 'Clear', action: () => { onClear(); setExpanded(false); }, color: 'tx-2', testId: 'clear-terminal-button' },
    { icon: Square, label: 'Stop', action: () => { onStop(); setExpanded(false); }, color: 'c-red', testId: 'stop-execution-button' },
  ];

  return (
    <div
      className="fixed z-50 bottom-5 right-5"
      onMouseEnter={cancelHide}
      onMouseLeave={startHide}
      data-testid="air-command-hub"
    >
      {expanded && (
        <div className="glass-panel p-1.5 mb-2 fade-up min-w-[180px]" data-testid="hub-menu">
          <div className="px-2 py-1 tx-3 text-[10px] font-bold uppercase tracking-wider">Quick Toggles</div>
          {quickActions.map((a, i) => (
            <HubBtn key={i} {...a} />
          ))}
          <div className="border-t bdr my-1" />
          <div className="px-2 py-1 tx-3 text-[10px] font-bold uppercase tracking-wider">Panels</div>
          {panelActions.map((a, i) => (
            <HubBtn key={i} {...a} />
          ))}
          <div className="border-t bdr my-1" />
          {utilActions.map((a, i) => (
            <HubBtn key={i} {...a} />
          ))}
        </div>
      )}

      <button
        onClick={() => setExpanded(!expanded)}
        className="w-12 h-12 glass-panel flex items-center justify-center c-green hover:c-cyan transition-all relative"
        style={{ borderRadius: 14 }}
        data-testid="expand-hub-button"
      >
        <span className="text-lg font-black">A</span>
        {recording && <span className="absolute -top-0.5 -right-0.5 w-2.5 h-2.5 rounded-full rec-pulse" style={{background:'var(--red)'}} />}
      </button>
    </div>
  );
}

function HubBtn({ icon: Icon, label, action, active, color, testId }) {
  return (
    <button onClick={action}
      className={`flex items-center gap-2.5 w-full px-3 py-1.5 rounded-lg text-xs transition-colors bg-h ${color} ${active ? 'bg-2' : ''}`}
      data-testid={testId}>
      <Icon size={14} />
      <span>{label}</span>
      {active && <span className="ml-auto w-1.5 h-1.5 rounded-full" style={{background:'var(--green)'}} />}
    </button>
  );
}
