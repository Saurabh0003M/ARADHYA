import React, { useState } from 'react';
import { Copy, Check } from 'lucide-react';

export default function Terminal({ messages, loading, chatEndRef, assistantName }) {
  return (
    <div className="flex-1 overflow-y-auto px-4 py-3 space-y-1" data-testid="terminal-output">
      {messages.length === 0 && <WelcomeBanner name={assistantName} />}
      {messages.map((msg, i) => <MsgLine key={i} msg={msg} name={assistantName} />)}
      {loading && (
        <div className="tx-2 text-xs fade-up" data-testid="loading-indicator">
          <span className="c-yellow">[{assistantName}]</span> <span className="blink">_</span> processing...
        </div>
      )}
      <div ref={chatEndRef} />
    </div>
  );
}

function WelcomeBanner({ name }) {
  return (
    <div className="py-8 fade-up" data-testid="welcome-screen">
      <pre className="c-green text-xs leading-tight mb-4">{`
   ___              __  __         
  / _ | _______ ___/ / / /  __ _____ _
 / __ |/ __/ _ \`/ _  / / _ \\/ // / _ \`/
/_/ |_/_/  \\_,_/\\_,_/ /_//_/\\_, /\\_,_/ 
                           /___/       `}</pre>
      <div className="tx-2 text-xs space-y-1">
        <p><span className="c-green">[OK]</span> {name} Agentic Coding Assistant v2.0</p>
        <p><span className="c-green">[OK]</span> Ready. Just tell me what you need in natural language.</p>
        <p className="tx-3 mt-3">  Examples:</p>
        <p className="tx-3">  "Keep my screen on until this download finishes then shutdown"</p>
        <p className="tx-3">  "Find all screenshots on my drive"</p>
        <p className="tx-3">  "Open whatsapp and fill the google form from my college group"</p>
        <p className="tx-3">  "Deploy an AI model to cloud - guide me step by step"</p>
        <p className="tx-3">  "Change my laptop to dark mode"</p>
        <p className="tx-3 mt-2">  Use the floating <span className="c-green">A</span> button (bottom-right) for quick toggles & panels.</p>
      </div>
    </div>
  );
}

function MsgLine({ msg, name }) {
  if (msg.role === 'user') {
    return (
      <div className="fade-up" data-testid="user-message">
        <span className="c-blue text-xs">[you]</span>{' '}
        <span className="tx-1 text-sm">{msg.content}</span>
      </div>
    );
  }
  if (msg.role === 'system') {
    return <div className="fade-up c-red text-xs" data-testid="system-message">{msg.content}</div>;
  }
  return <AsstMsg content={msg.content} name={name} />;
}

function AsstMsg({ content, name }) {
  const blocks = parseContent(content);
  return (
    <div className="fade-up my-2" data-testid="assistant-message">
      <div className="text-xs mb-1"><span className="c-green">[{name}]</span></div>
      <div className="pl-2 space-y-1" style={{ borderLeft: '2px solid var(--green)', borderLeftColor: 'color-mix(in srgb, var(--green) 30%, transparent)' }}>
        {blocks.map((b, i) => b.type === 'code' ? <CodeBlock key={i} code={b.content} lang={b.lang} /> : <TextBlock key={i} text={b.content} />)}
      </div>
    </div>
  );
}

function CodeBlock({ code, lang }) {
  const [copied, setCopied] = useState(false);
  const copy = () => { navigator.clipboard.writeText(code); setCopied(true); setTimeout(() => setCopied(false), 2000); };
  return (
    <div className="code-block my-2 group" data-testid="code-block">
      <div className="code-header">
        <span>{lang || 'shell'}</span>
        <button onClick={copy} className="opacity-0 group-hover:opacity-100 transition-opacity tx-3 hover:tx-1" data-testid="copy-code-button">
          {copied ? <Check size={12} /> : <Copy size={12} />}
        </button>
      </div>
      <pre className="code-body">
        {code.split('\n').map((line, i) => {
          const t = line.trim();
          if (t.startsWith('#') || t.startsWith('//') || t.startsWith('REM '))
            return <div key={i}><span className="cmt">{line}</span></div>;
          return <div key={i}>{line}</div>;
        })}
      </pre>
    </div>
  );
}

function TextBlock({ text }) {
  return (
    <div className="text-sm tx-2 leading-relaxed">
      {text.split('\n').map((line, i) => {
        if (line.startsWith('[OK]') || line.startsWith('[INFO]')) return <p key={i} className="c-green">{fmt(line)}</p>;
        if (line.startsWith('[WARN]')) return <p key={i} className="c-yellow">{fmt(line)}</p>;
        if (line.startsWith('[ERR]')) return <p key={i} className="c-red">{fmt(line)}</p>;
        if (line.startsWith('### ')) return <p key={i} className="tx-1 font-bold mt-2">{fmt(line.slice(4))}</p>;
        if (line.startsWith('## ')) return <p key={i} className="tx-1 font-bold text-base mt-2">{fmt(line.slice(3))}</p>;
        if (line.startsWith('- ') || line.startsWith('* ')) return <p key={i} className="pl-3">{fmt(line)}</p>;
        if (/^\d+\.\s/.test(line)) return <p key={i} className="pl-3">{fmt(line)}</p>;
        if (line.trim() === '') return <div key={i} className="h-1" />;
        return <p key={i}>{fmt(line)}</p>;
      })}
    </div>
  );
}

function fmt(text) {
  return text.split(/(`[^`]+`)/g).map((p, i) => {
    if (p.startsWith('`') && p.endsWith('`')) return <code key={i} className="bg-2 px-1 rounded c-cyan text-xs">{p.slice(1, -1)}</code>;
    return p.split(/(\*\*[^*]+\*\*)/g).map((s, j) => {
      if (s.startsWith('**') && s.endsWith('**')) return <strong key={`${i}-${j}`} className="tx-1">{s.slice(2, -2)}</strong>;
      return s;
    });
  });
}

function parseContent(text) {
  const blocks = [];
  const rx = /```(\w*)\n?([\s\S]*?)```/g;
  let last = 0, m;
  while ((m = rx.exec(text)) !== null) {
    if (m.index > last) { const t = text.slice(last, m.index).trim(); if (t) blocks.push({ type: 'text', content: t }); }
    blocks.push({ type: 'code', content: m[2].trim(), lang: m[1] || 'shell' });
    last = m.index + m[0].length;
  }
  if (last < text.length) { const t = text.slice(last).trim(); if (t) blocks.push({ type: 'text', content: t }); }
  if (!blocks.length) blocks.push({ type: 'text', content: text });
  return blocks;
}
