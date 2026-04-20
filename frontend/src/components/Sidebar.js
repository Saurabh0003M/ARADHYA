import React from 'react';
import { Keyboard, Monitor, Zap, Shield, ChevronRight, Volume2 } from 'lucide-react';

export default function Sidebar({ open, onClose, templates, voicePresets, settings, onTemplateClick, onSettingsChange, onVoiceChange }) {
  return (
    <>
      {open && <div className="fixed inset-0 bg-black/20 z-30 md:hidden" onClick={onClose} />}
      <aside
        className={`fixed md:relative z-40 md:z-0 top-0 left-0 h-full w-72 lg:w-80 border-r border-black/10 bg-white flex-shrink-0 flex flex-col transition-transform duration-300 ${
          open ? 'translate-x-0' : '-translate-x-full md:translate-x-0'
        } md:flex`}
        data-testid="sidebar"
      >
        <div className="p-5 border-b border-black/10">
          <h2 className="font-heading font-bold text-lg tracking-tight" data-testid="sidebar-title">Control Panel</h2>
          <p className="text-xs text-[#52525B] mt-1">Configure Aradhya's behavior</p>
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-6">
          {/* Keyboard Shortcuts */}
          <section data-testid="shortcuts-section">
            <div className="flex items-center gap-2 mb-3">
              <Keyboard size={14} className="text-[#52525B]" />
              <span className="text-xs font-bold uppercase tracking-[0.2em] text-[#52525B]">Shortcuts</span>
            </div>
            <div className="space-y-2">
              <ShortcutRow keys={['Ctrl', 'Space']} label="Toggle Mic" />
              <ShortcutRow keys={['Ctrl', 'Enter']} label="Send Message" />
              <ShortcutRow keys={['Ctrl', 'K']} label="Command Mode" />
              <ShortcutRow keys={['Ctrl', 'Shift', 'S']} label="Search Mode" />
              <ShortcutRow keys={['Esc']} label="Clear Input" />
            </div>
          </section>

          {/* Voice Presets */}
          <section data-testid="voice-presets-section">
            <div className="flex items-center gap-2 mb-3">
              <Volume2 size={14} className="text-[#52525B]" />
              <span className="text-xs font-bold uppercase tracking-[0.2em] text-[#52525B]">Voice Preset</span>
            </div>
            <div className="space-y-1.5">
              {voicePresets.map(preset => (
                <button
                  key={preset.id}
                  onClick={() => onVoiceChange(preset.id)}
                  className={`w-full text-left px-3 py-2.5 rounded-lg text-sm transition-all ${
                    settings.voice_preset === preset.id
                      ? 'bg-[#18181B] text-white'
                      : 'bg-transparent hover:bg-black/5 text-[#09090B]'
                  }`}
                  data-testid={`voice-preset-${preset.id}`}
                >
                  <div className="font-medium">{preset.name}</div>
                  <div className={`text-xs mt-0.5 ${settings.voice_preset === preset.id ? 'text-white/60' : 'text-[#52525B]'}`}>
                    {preset.description}
                  </div>
                </button>
              ))}
            </div>
          </section>

          {/* Settings */}
          <section data-testid="settings-section">
            <div className="flex items-center gap-2 mb-3">
              <Shield size={14} className="text-[#52525B]" />
              <span className="text-xs font-bold uppercase tracking-[0.2em] text-[#52525B]">Safety</span>
            </div>
            <ToggleSwitch
              label="Security Filter"
              description="Filter malicious content from web searches"
              checked={settings.security_filter}
              onChange={() => onSettingsChange('security_filter')}
              testId="security-filter-toggle"
            />
          </section>

          {/* Command Templates */}
          <section data-testid="templates-section">
            <div className="flex items-center gap-2 mb-3">
              <Zap size={14} className="text-[#52525B]" />
              <span className="text-xs font-bold uppercase tracking-[0.2em] text-[#52525B]">Quick Commands</span>
            </div>
            <div className="space-y-1.5">
              {templates.map(tpl => (
                <button
                  key={tpl.id}
                  onClick={() => onTemplateClick(tpl)}
                  className="w-full text-left px-3 py-2.5 rounded-lg hover:bg-black/5 transition-all group"
                  data-testid={`template-${tpl.id}`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-[#09090B]">{tpl.title}</span>
                    <ChevronRight size={14} className="text-[#52525B] opacity-0 group-hover:opacity-100 transition-opacity" />
                  </div>
                  <div className="text-xs text-[#52525B] mt-0.5">{tpl.description}</div>
                  {tpl.level === 'admin' && (
                    <span className="text-[10px] bg-red-50 text-red-600 px-1.5 py-0.5 rounded mt-1 inline-block border border-red-200">Admin</span>
                  )}
                </button>
              ))}
            </div>
          </section>
        </div>
      </aside>
    </>
  );
}

function ShortcutRow({ keys, label }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-xs text-[#52525B]">{label}</span>
      <div className="flex items-center gap-1">
        {keys.map((k, i) => (
          <React.Fragment key={i}>
            <kbd>{k}</kbd>
            {i < keys.length - 1 && <span className="text-[#52525B] text-[10px]">+</span>}
          </React.Fragment>
        ))}
      </div>
    </div>
  );
}

function ToggleSwitch({ label, description, checked, onChange, testId }) {
  return (
    <div className="flex items-start justify-between gap-3 py-1">
      <div>
        <div className="text-sm font-medium">{label}</div>
        {description && <div className="text-xs text-[#52525B] mt-0.5">{description}</div>}
      </div>
      <button
        onClick={onChange}
        className={`relative flex-shrink-0 w-10 h-6 rounded-full transition-colors ${checked ? 'bg-[#18181B]' : 'bg-gray-200'}`}
        data-testid={testId}
      >
        <span className={`absolute top-1 left-1 w-4 h-4 rounded-full bg-white transition-transform shadow-sm ${checked ? 'translate-x-4' : ''}`} />
      </button>
    </div>
  );
}
