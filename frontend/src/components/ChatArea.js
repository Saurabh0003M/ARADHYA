import React, { useEffect, useState } from 'react';
import MessageBubble from './MessageBubble';
import { Sparkles } from 'lucide-react';

export default function ChatArea({ messages, loading, chatEndRef }) {
  return (
    <div className="flex-1 overflow-y-auto p-4 md:p-8 space-y-6 pb-40 scroll-smooth" data-testid="chat-area">
      {messages.length === 0 && <WelcomeScreen />}
      {messages.map((msg, i) => (
        <div
          key={i}
          className="chat-message-appear"
          style={{ animationDelay: `${i * 0.05}s` }}
        >
          <MessageBubble message={msg} />
        </div>
      ))}
      {loading && <TypingIndicator />}
      <div ref={chatEndRef} />
    </div>
  );
}

function WelcomeScreen() {
  const [show, setShow] = useState(false);
  useEffect(() => { setShow(true); }, []);

  return (
    <div className={`flex flex-col items-center justify-center min-h-[60vh] text-center transition-all duration-700 ${show ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8'}`} data-testid="welcome-screen">
      <img
        src="https://static.prod-images.emergentagent.com/jobs/705898cf-9bcf-4e96-bf29-2ad7fa8e7d91/images/bdd0acceffeaa877f8337151b8ea0f0a7a43911f32fe8e49106382894ddb3f73.png"
        alt="Aradhya"
        className="w-20 h-20 rounded-2xl mb-6 shadow-lg"
      />
      <h2 className="font-heading font-black text-3xl sm:text-4xl tracking-tighter mb-3">
        Hello, I'm Aradhya
      </h2>
      <p className="text-[#52525B] max-w-md text-base leading-relaxed mb-8">
        Your Operating Intelligence. I craft system commands, search the web safely, and help you control your machine with natural language.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 max-w-lg w-full">
        <QuickAction icon="terminal" label="Generate a command" hint="Try: keep screen on" />
        <QuickAction icon="globe" label="Search the web" hint="Safe & filtered" />
        <QuickAction icon="mic" label="Voice input" hint="Ctrl + Space" />
      </div>
    </div>
  );
}

function QuickAction({ label, hint }) {
  return (
    <div className="bg-white border border-black/10 rounded-xl p-4 text-left hover:border-black/20 transition-colors cursor-default" data-testid={`quick-action-${label.toLowerCase().replace(/\s/g, '-')}`}>
      <div className="text-sm font-medium text-[#09090B]">{label}</div>
      <div className="text-xs text-[#52525B] mt-1">{hint}</div>
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="flex items-start gap-3" data-testid="typing-indicator">
      <div className="w-8 h-8 rounded-lg bg-[#18181B] flex items-center justify-center flex-shrink-0">
        <Sparkles size={14} className="text-white" />
      </div>
      <div className="bg-white border border-black/10 rounded-2xl rounded-tl-sm px-5 py-4 shadow-sm">
        <div className="flex gap-1.5">
          <span className="w-2 h-2 rounded-full bg-[#52525B] animate-bounce" style={{ animationDelay: '0ms' }} />
          <span className="w-2 h-2 rounded-full bg-[#52525B] animate-bounce" style={{ animationDelay: '150ms' }} />
          <span className="w-2 h-2 rounded-full bg-[#52525B] animate-bounce" style={{ animationDelay: '300ms' }} />
        </div>
      </div>
    </div>
  );
}
