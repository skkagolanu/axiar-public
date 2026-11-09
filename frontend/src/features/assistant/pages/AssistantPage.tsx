import { useEffect, useRef, useState } from 'react';
import api from '@/lib/axios';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { toast } from '@/hooks/use-toast';
import { Sparkles, Send, Loader2, User, BookOpen, ChevronDown, ChevronUp } from 'lucide-react';
import type { CooMessage, CooResponse } from '../types';

const SUGGESTIONS = [
  'How did revenue look over the last 30 days?',
  'What is our booking completion rate this month?',
  'When are we busiest during the day?',
  'What is the demand forecast for the next two weeks?',
];

function uid() {
  return typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : String(Date.now() + Math.random());
}

export default function AssistantPage() {
  const [messages, setMessages] = useState<CooMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const [kbOpen, setKbOpen] = useState(false);
  const [kbTitle, setKbTitle] = useState('');
  const [kbContent, setKbContent] = useState('');
  const [kbIngesting, setKbIngesting] = useState(false);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const send = async (question?: string) => {
    const q = (question ?? input).trim();
    if (!q || loading) return;

    setMessages((m) => [...m, { id: uid(), role: 'user', content: q }]);
    setInput('');
    setLoading(true);

    try {
      const res = await api.post<CooResponse>('/api/v1/ai/coo', { question: q });
      setMessages((m) => [
        ...m,
        {
          id: uid(),
          role: 'assistant',
          content: res.data.answer,
          toolsUsed: res.data.tools_used,
          data: res.data.data,
        },
      ]);
    } catch (err) {
      console.error('COO request failed', err);
      toast({
        variant: 'destructive',
        title: 'Assistant unavailable',
        description: 'Could not reach the Virtual COO. Try again shortly.',
      });
      setMessages((m) => [
        ...m,
        { id: uid(), role: 'assistant', content: 'Sorry, I could not reach the assistant just now.', error: true },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const ingestDocument = async () => {
    if (!kbTitle.trim() || !kbContent.trim()) return;
    setKbIngesting(true);
    try {
      await api.post('/api/v1/ai/ingest', { documents: [{ title: kbTitle.trim(), content: kbContent.trim() }] });
      toast({ title: 'Added to knowledge base', description: `"${kbTitle}" is now available to the COO assistant.` });
      setKbTitle('');
      setKbContent('');
      setKbOpen(false);
    } catch {
      toast({ variant: 'destructive', title: 'Ingest failed', description: 'Could not add document. Try again.' });
    } finally {
      setKbIngesting(false);
    }
  };

  return (
    <div className="flex h-full flex-col bg-slate-50">
      {/* Header */}
      <div className="flex items-center gap-3 border-b border-slate-200 bg-white px-6 py-4">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-violet-600 to-indigo-600 text-white">
          <Sparkles className="h-5 w-5" />
        </div>
        <div>
          <h2 className="font-heading text-lg font-bold text-slate-900">Virtual COO</h2>
          <p className="text-xs text-slate-500">Ask about revenue, bookings, demand and capacity — answered from your live data.</p>
        </div>
      </div>

      {/* Conversation */}
      <div className="flex-1 overflow-y-auto p-4 md:p-6">
        {messages.length === 0 ? (
          <div className="mx-auto max-w-xl py-10 text-center">
            <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br from-violet-600 to-indigo-600 text-white">
              <Sparkles className="h-6 w-6" />
            </div>
            <h3 className="font-heading text-xl font-bold text-slate-900">Your AI operations advisor</h3>
            <p className="mt-1 text-sm text-slate-500">Try one of these to get started:</p>
            <div className="mt-4 grid gap-2 sm:grid-cols-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => send(s)}
                  className="rounded-lg border border-slate-200 bg-white p-3 text-left text-sm text-slate-700 transition-colors hover:border-violet-300 hover:bg-violet-50"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="mx-auto max-w-3xl space-y-4">
            {messages.map((m) => (
              <MessageBubble key={m.id} message={m} />
            ))}
            {loading && (
              <div className="flex items-center gap-2 text-sm text-slate-500">
                <Loader2 className="h-4 w-4 animate-spin" /> Crunching your numbers…
              </div>
            )}
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Composer */}
      <div className="border-t border-slate-200 bg-white p-4">
        <div className="mx-auto flex max-w-3xl items-end gap-2">
          <Textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
            placeholder="Ask your Virtual COO…  (Enter to send, Shift+Enter for a new line)"
            rows={1}
            className="max-h-40 min-h-[44px] flex-1 resize-none bg-white"
          />
          <Button
            onClick={() => send()}
            disabled={loading || !input.trim()}
            className="h-11 bg-gradient-to-r from-violet-600 to-indigo-600 text-white shadow-lg shadow-violet-500/20 hover:from-violet-500 hover:to-indigo-500"
          >
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
          </Button>
        </div>

        {/* Knowledge base ingest panel */}
        <div className="mx-auto mt-3 max-w-3xl">
          <button
            onClick={() => setKbOpen((o) => !o)}
            className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-violet-600 transition-colors"
          >
            <BookOpen className="h-3.5 w-3.5" />
            Add to knowledge base
            {kbOpen ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
          </button>
          {kbOpen && (
            <div className="mt-2 space-y-2 rounded-lg border border-slate-200 bg-slate-50 p-3">
              <Input
                placeholder="Title (e.g. Q1 pricing guidelines)"
                value={kbTitle}
                onChange={(e) => setKbTitle(e.target.value)}
                className="bg-white text-sm"
              />
              <Textarea
                placeholder="Paste document content here — the COO assistant will cite this when answering questions."
                value={kbContent}
                onChange={(e) => setKbContent(e.target.value)}
                rows={4}
                className="resize-none bg-white text-sm"
              />
              <div className="flex justify-end">
                <Button
                  size="sm"
                  onClick={ingestDocument}
                  disabled={kbIngesting || !kbTitle.trim() || !kbContent.trim()}
                  className="bg-gradient-to-r from-violet-600 to-indigo-600 text-white"
                >
                  {kbIngesting ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <BookOpen className="mr-1.5 h-3.5 w-3.5" />}
                  {kbIngesting ? 'Adding…' : 'Add document'}
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function MessageBubble({ message }: { message: CooMessage }) {
  const isUser = message.role === 'user';

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="flex max-w-[85%] items-start gap-2">
          <div className="rounded-2xl rounded-tr-sm bg-gradient-to-r from-violet-600 to-indigo-600 px-4 py-2.5 text-sm text-white shadow">
            {message.content}
          </div>
          <div className="mt-0.5 flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full bg-slate-200 text-slate-600">
            <User className="h-4 w-4" />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start">
      <div className="flex max-w-[85%] items-start gap-2">
        <div className="mt-0.5 flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-violet-600 to-indigo-600 text-white">
          <Sparkles className="h-4 w-4" />
        </div>
        <div
          className={cn(
            'rounded-2xl rounded-tl-sm border px-4 py-2.5 text-sm shadow-sm',
            message.error ? 'border-red-200 bg-red-50 text-red-700' : 'border-slate-200 bg-white text-slate-900'
          )}
        >
          <p className="whitespace-pre-wrap">{message.content}</p>

          {message.toolsUsed && message.toolsUsed.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1">
              {message.toolsUsed.map((t) => (
                <span key={t} className="rounded-full bg-violet-100 px-2 py-0.5 text-[11px] font-medium text-violet-700">
                  {t}
                </span>
              ))}
            </div>
          )}

          {message.data && Object.keys(message.data).length > 0 && (
            <details className="mt-2">
              <summary className="cursor-pointer text-[11px] font-medium text-slate-400 hover:text-slate-600">
                View data
              </summary>
              <pre className="mt-1 overflow-x-auto rounded-md bg-slate-900 p-2 text-[11px] leading-relaxed text-slate-100">
                {JSON.stringify(message.data, null, 2)}
              </pre>
            </details>
          )}
        </div>
      </div>
    </div>
  );
}
