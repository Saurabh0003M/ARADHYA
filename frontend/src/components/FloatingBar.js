import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Mic, Monitor, Sparkles, Globe, Send, Terminal, Search, MicOff } from 'lucide-react';

export default function FloatingBar({ onSend, loading, settings, onToggle, activeMode, onModeChange, voicePresets }) {
  const [text, setText] = useState('');
  const [recording, setRecording] = useState(false);
  const inputRef = useRef(null);
  const recognitionRef = useRef(null);

  const handleSubmit = useCallback(() => {
    if (!text.trim() || loading) return;
    onSend(text.trim(), activeMode);
    setText('');
  }, [text, loading, onSend, activeMode]);

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e) => {
      // Ctrl+Space: toggle mic
      if (e.ctrlKey && e.code === 'Space') {
        e.preventDefault();
        toggleRecording();
        return;
      }
      // Ctrl+K: command mode
      if (e.ctrlKey && e.key === 'k') {
        e.preventDefault();
        onModeChange('command');
        inputRef.current?.focus();
        return;
      }
      // Ctrl+Shift+S: search mode
      if (e.ctrlKey && e.shiftKey && e.key === 'S') {
        e.preventDefault();
        onModeChange('search');
        inputRef.current?.focus();
        return;
      }
      // Escape: clear
      if (e.key === 'Escape') {
        setText('');
        onModeChange('chat');
        return;
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onModeChange]);

  const toggleRecording = useCallback(() => {
    if (recording) {
      if (recognitionRef.current) {
        recognitionRef.current.stop();
      }
      setRecording(false);
      return;
    }

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      alert('Speech recognition not supported in this browser. Try Chrome or Edge.');
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = 'en-US';

    recognition.onresult = (event) => {
      const transcript = Array.from(event.results)
        .map(r => r[0].transcript)
        .join('');
      setText(transcript);
    };

    recognition.onend = () => {
      setRecording(false);
    };

    recognition.onerror = () => {
      setRecording(false);
    };

    recognitionRef.current = recognition;
    recognition.start();
    setRecording(true);
  }, [recording]);

  // Speak assistant responses
  useEffect(() => {
    window.__aradhyaSpeak = (text) => {
      const utterance = new SpeechSynthesisUtterance(text);
      const preset = voicePresets.find(p => p.id === settings.voice_preset);
      if (preset?.settings) {
        utterance.rate = preset.settings.rate || 1;
        utterance.pitch = preset.settings.pitch || 1;
        utterance.lang = preset.settings.lang || 'en-US';
        
        const voices = window.speechSynthesis.getVoices();
        if (preset.settings.voiceURI === 'female') {
          const femaleVoice = voices.find(v =>
            v.name.toLowerCase().includes('female') ||
            v.name.toLowerCase().includes('zira') ||
            v.name.toLowerCase().includes('samantha') ||
            v.name.toLowerCase().includes('google us english')
          );
          if (femaleVoice) utterance.voice = femaleVoice;
        } else if (preset.settings.voiceURI === 'male') {
          const maleVoice = voices.find(v =>
            v.name.toLowerCase().includes('male') ||
            v.name.toLowerCase().includes('david') ||
            v.name.toLowerCase().includes('daniel')
          );
          if (maleVoice) utterance.voice = maleVoice;
        }
      }
      window.speechSynthesis.speak(utterance);
    };
  }, [settings.voice_preset, voicePresets]);

  const modeConfig = {
    chat: { icon: Sparkles, label: 'Chat with Aradhya', color: '' },
    command: { icon: Terminal, label: 'Generate a command...', color: 'text-[#4ADE80]' },
    search: { icon: Search, label: 'Search the web safely...', color: 'text-[#2563EB]' },
  };

  const currentMode = modeConfig[activeMode] || modeConfig.chat;
  const ModeIcon = currentMode.icon;

  return (
    <div className="absolute bottom-6 left-1/2 -translate-x-1/2 w-[calc(100%-2rem)] max-w-2xl z-50" data-testid="floating-bar">
      {/* Mode indicator */}
      {activeMode !== 'chat' && (
        <div className="flex justify-center mb-2">
          <span className={`text-xs font-mono uppercase tracking-widest px-3 py-1 rounded-full bg-white border border-black/10 shadow-sm ${currentMode.color}`} data-testid="mode-indicator">
            {activeMode === 'command' ? 'Command Mode' : 'Search Mode'}
            <button onClick={() => onModeChange('chat')} className="ml-2 text-[#52525B] hover:text-[#09090B]">x</button>
          </span>
        </div>
      )}

      <div className="glass-bar rounded-2xl flex items-center p-2 gap-1" data-testid="floating-bar-inner">
        {/* Floating control buttons */}
        <ControlButton
          icon={recording ? MicOff : Mic}
          label="Mic"
          active={recording}
          alert={recording}
          onClick={toggleRecording}
          shortcut="Ctrl+Space"
          testId="mic-toggle-button"
        />
        <ControlButton
          icon={Monitor}
          label="Screen"
          active={settings.screen_context}
          onClick={() => onToggle('screen_context')}
          testId="screen-toggle-button"
        />
        <ControlButton
          icon={Sparkles}
          label="A"
          active={settings.advanced_mode}
          onClick={() => onToggle('advanced_mode')}
          testId="advanced-toggle-button"
        />
        <ControlButton
          icon={Globe}
          label="I"
          active={settings.interaction_enabled}
          onClick={() => onToggle('interaction_enabled')}
          testId="interaction-toggle-button"
        />

        <div className="w-px h-8 bg-black/10 mx-1" />

        {/* Mode toggles */}
        <button
          onClick={() => onModeChange(activeMode === 'command' ? 'chat' : 'command')}
          className={`p-2 rounded-lg transition-all ${activeMode === 'command' ? 'bg-[#18181B] text-white' : 'hover:bg-black/5 text-[#52525B]'}`}
          title="Command Mode (Ctrl+K)"
          data-testid="command-mode-button"
        >
          <Terminal size={16} />
        </button>
        <button
          onClick={() => onModeChange(activeMode === 'search' ? 'chat' : 'search')}
          className={`p-2 rounded-lg transition-all ${activeMode === 'search' ? 'bg-[#2563EB] text-white' : 'hover:bg-black/5 text-[#52525B]'}`}
          title="Search Mode (Ctrl+Shift+S)"
          data-testid="search-mode-button"
        >
          <Search size={16} />
        </button>

        <div className="w-px h-8 bg-black/10 mx-1" />

        {/* Input */}
        <div className="flex-1 flex items-center relative">
          <ModeIcon size={14} className={`absolute left-3 ${currentMode.color || 'text-[#52525B]'}`} />
          <input
            ref={inputRef}
            type="text"
            value={text}
            onChange={e => setText(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSubmit(); } }}
            placeholder={currentMode.label}
            className="w-full bg-transparent border-none focus:ring-0 text-sm placeholder:text-gray-400 py-3 pl-9 pr-3 outline-none font-body"
            data-testid="chat-input"
          />
        </div>

        {/* Send */}
        <button
          onClick={handleSubmit}
          disabled={!text.trim() || loading}
          className="bg-[#18181B] text-white hover:bg-[#18181B]/90 rounded-xl p-3 transition-all active:scale-95 disabled:opacity-30 disabled:cursor-not-allowed"
          data-testid="send-button"
        >
          <Send size={16} />
        </button>
      </div>
    </div>
  );
}

function ControlButton({ icon: Icon, label, active, alert, onClick, shortcut, testId }) {
  return (
    <button
      onClick={onClick}
      className={`relative h-11 w-11 rounded-xl flex flex-col items-center justify-center transition-all ${
        active
          ? alert
            ? 'bg-red-500/10 text-red-500 shadow-inner'
            : 'bg-black/10 text-[#09090B] shadow-inner'
          : 'bg-transparent hover:bg-black/5 text-[#52525B]'
      } ${alert ? 'mic-recording' : ''}`}
      title={shortcut ? `${label} (${shortcut})` : label}
      data-active={active}
      data-testid={testId}
    >
      <Icon size={16} />
      <span className="text-[9px] font-medium mt-0.5 leading-none">{label}</span>
    </button>
  );
}
