import React, { useState } from 'react';
import { Sparkles, Copy, Check, AlertTriangle } from 'lucide-react';

export default function MessageBubble({ message }) {
  if (message.role === 'user') return <UserBubble message={message} />;
  return <AssistantBubble message={message} />;
}

function UserBubble({ message }) {
  return (
    <div className="flex justify-end" data-testid="user-message">
      <div className="bg-gray-100 text-[#09090B] rounded-2xl rounded-tr-sm px-5 py-3.5 max-w-[80%] shadow-sm border border-black/5">
        <p className="text-sm leading-relaxed whitespace-pre-wrap">{message.content}</p>
        {message.mode && message.mode !== 'chat' && (
          <span className="text-[10px] uppercase tracking-wider text-[#52525B] mt-1.5 inline-block font-mono">
            {message.mode === 'command' ? 'Command Mode' : 'Search Mode'}
          </span>
        )}
      </div>
    </div>
  );
}

function AssistantBubble({ message }) {
  const parsed = parseContent(message.content);

  return (
    <div className="flex items-start gap-3" data-testid="assistant-message">
      <div className="w-8 h-8 rounded-lg bg-[#18181B] flex items-center justify-center flex-shrink-0 mt-0.5">
        <Sparkles size={14} className="text-white" />
      </div>
      <div className="bg-white border border-black/10 shadow-sm rounded-2xl rounded-tl-sm px-5 py-4 max-w-[85%]">
        <div className="markdown-content text-sm text-[#09090B]">
          {parsed.map((block, i) => {
            if (block.type === 'code') return <TerminalBlock key={i} code={block.content} language={block.language} />;
            if (block.type === 'warning') return <WarningBlock key={i} text={block.content} />;
            return <TextBlock key={i} text={block.content} />;
          })}
        </div>
      </div>
    </div>
  );
}

function TerminalBlock({ code, language }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="terminal-block my-3 group relative" data-testid="terminal-block">
      <div className="terminal-header">
        <div className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full bg-red-500/70" />
          <span className="w-2.5 h-2.5 rounded-full bg-yellow-500/70" />
          <span className="w-2.5 h-2.5 rounded-full bg-green-500/70" />
          <span className="ml-2">{language || 'shell'}</span>
        </div>
        <button
          onClick={handleCopy}
          className="opacity-0 group-hover:opacity-100 transition-opacity bg-white/10 hover:bg-white/20 text-white rounded p-1.5"
          data-testid="copy-command-button"
        >
          {copied ? <Check size={14} /> : <Copy size={14} />}
        </button>
      </div>
      <div className="terminal-body">
        {formatCode(code)}
      </div>
    </div>
  );
}

function WarningBlock({ text }) {
  return (
    <div className="flex items-start gap-2 bg-red-50 border border-red-200 rounded-lg p-3 my-2" data-testid="warning-block">
      <AlertTriangle size={16} className="text-red-500 flex-shrink-0 mt-0.5" />
      <p className="text-xs text-red-700 leading-relaxed">{text}</p>
    </div>
  );
}

function TextBlock({ text }) {
  const lines = text.split('\n');
  return (
    <>
      {lines.map((line, i) => {
        if (line.startsWith('### ')) return <h3 key={i} className="font-heading font-semibold text-base mt-3 mb-1">{line.slice(4)}</h3>;
        if (line.startsWith('## ')) return <h2 key={i} className="font-heading font-bold text-lg mt-3 mb-1">{line.slice(3)}</h2>;
        if (line.startsWith('# ')) return <h1 key={i} className="font-heading font-black text-xl mt-3 mb-1">{line.slice(2)}</h1>;
        if (line.startsWith('- ') || line.startsWith('* ')) return <li key={i} className="ml-4 mb-1 text-sm list-disc">{formatInline(line.slice(2))}</li>;
        if (/^\d+\.\s/.test(line)) return <li key={i} className="ml-4 mb-1 text-sm list-decimal">{formatInline(line.replace(/^\d+\.\s/, ''))}</li>;
        if (line.trim() === '') return <div key={i} className="h-2" />;
        return <p key={i} className="mb-1.5 text-sm leading-relaxed">{formatInline(line)}</p>;
      })}
    </>
  );
}

function formatInline(text) {
  const parts = text.split(/(`[^`]+`)/g);
  return parts.map((part, i) => {
    if (part.startsWith('`') && part.endsWith('`')) {
      return <code key={i} className="bg-black/5 px-1.5 py-0.5 rounded text-[0.8em] font-mono">{part.slice(1, -1)}</code>;
    }
    const boldParts = part.split(/(\*\*[^*]+\*\*)/g);
    return boldParts.map((bp, j) => {
      if (bp.startsWith('**') && bp.endsWith('**')) {
        return <strong key={`${i}-${j}`}>{bp.slice(2, -2)}</strong>;
      }
      return bp;
    });
  });
}

function formatCode(code) {
  return code.split('\n').map((line, i) => {
    const trimmed = line.trim();
    if (trimmed.startsWith('#') || trimmed.startsWith('//') || trimmed.startsWith('REM ')) {
      return <div key={i}><span className="comment">{line}</span></div>;
    }
    return <div key={i}>{line}</div>;
  });
}

function parseContent(text) {
  const blocks = [];
  const codeRegex = /```(\w*)\n?([\s\S]*?)```/g;
  let lastIndex = 0;
  let match;

  while ((match = codeRegex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      const preText = text.slice(lastIndex, match.index).trim();
      if (preText) {
        if (preText.toLowerCase().includes('warning') || preText.toLowerCase().includes('caution') || preText.toLowerCase().includes('requires admin')) {
          blocks.push({ type: 'warning', content: preText });
        } else {
          blocks.push({ type: 'text', content: preText });
        }
      }
    }
    blocks.push({ type: 'code', content: match[2].trim(), language: match[1] || 'shell' });
    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < text.length) {
    const remaining = text.slice(lastIndex).trim();
    if (remaining) blocks.push({ type: 'text', content: remaining });
  }

  if (blocks.length === 0) blocks.push({ type: 'text', content: text });
  return blocks;
}
