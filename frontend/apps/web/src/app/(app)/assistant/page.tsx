"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { Sparkles, Send, Plus, ChevronDown, ChevronRight, Loader2, Paperclip, X } from "lucide-react";
import { streamChat, aiApi } from "@/lib/api";
import type { AiConversation } from "@/lib/api";

// ── Local types ───────────────────────────────────────────────────────────────

interface ToolCallDisplay {
  name: string;
  result: unknown;
}

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  toolCalls?: ToolCallDisplay[];
  isStreaming?: boolean;
}

interface PendingDraftLine {
  account_code: string;
  account_name: string;
  debit: string;
  credit: string;
}

interface PendingDraft {
  draftId: string;
  proposedEntry: {
    date: string;
    description: string;
    lines: PendingDraftLine[];
    total_debit: string;
  };
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function uid(): string {
  return Math.random().toString(36).slice(2);
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
  } catch {
    return iso;
  }
}

/** Very simple inline markdown: **bold**, *italic*, `code` */
function renderInlineMarkdown(text: string): string {
  return text
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    .replace(/`(.+?)`/g, "<code class=\"bg-muted px-1 rounded text-xs\">$1</code>");
}

// ── Sub-components ────────────────────────────────────────────────────────────

function ToolCallChip({ toolCall }: { toolCall: ToolCallDisplay }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-1">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1 rounded-full bg-muted/60 px-2 py-0.5 text-xs text-muted-foreground hover:bg-muted transition-colors"
      >
        {open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
        🔧 {toolCall.name}
      </button>
      {open && (
        <pre className="mt-1 max-h-40 overflow-auto rounded-md bg-muted/40 p-2 text-xs text-muted-foreground whitespace-pre-wrap break-all">
          {JSON.stringify(toolCall.result, null, 2)}
        </pre>
      )}
    </div>
  );
}

function ConfirmationCard({
  draft,
  onPost,
  onCancel,
}: {
  draft: PendingDraft;
  onPost: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="mt-3 rounded-xl border border-primary/30 bg-card shadow-sm overflow-hidden">
      <div className="bg-primary/5 px-4 py-2.5 border-b border-primary/20">
        <p className="text-sm font-semibold text-primary">Review Journal Entry</p>
        <p className="text-xs text-muted-foreground mt-0.5">
          {draft.proposedEntry.date} — {draft.proposedEntry.description}
        </p>
      </div>
      <div className="px-4 py-3">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-left text-muted-foreground border-b">
              <th className="pb-1.5 font-medium">Account</th>
              <th className="pb-1.5 font-medium text-right">Debit</th>
              <th className="pb-1.5 font-medium text-right">Credit</th>
            </tr>
          </thead>
          <tbody>
            {draft.proposedEntry.lines.map((line, i) => (
              <tr key={i} className="border-b border-muted/40 last:border-0">
                <td className="py-1.5">
                  <span className="font-mono text-muted-foreground mr-1.5">{line.account_code}</span>
                  {line.account_name}
                </td>
                <td className="py-1.5 text-right font-mono">
                  {line.debit !== "0.00" ? line.debit : ""}
                </td>
                <td className="py-1.5 text-right font-mono">
                  {line.credit !== "0.00" ? line.credit : ""}
                </td>
              </tr>
            ))}
            <tr className="font-semibold text-foreground">
              <td className="pt-2">Total</td>
              <td className="pt-2 text-right font-mono">{draft.proposedEntry.total_debit}</td>
              <td className="pt-2 text-right font-mono">{draft.proposedEntry.total_debit}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div className="flex gap-2 px-4 py-3 border-t bg-muted/20">
        <button
          onClick={onPost}
          className="flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
        >
          ✓ Post Entry
        </button>
        <button
          onClick={onCancel}
          className="flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium text-foreground hover:bg-muted transition-colors"
        >
          ✗ Cancel
        </button>
      </div>
    </div>
  );
}

function MessageBubble({
  message,
  pendingDraft,
  onPost,
  onCancel,
}: {
  message: ChatMessage;
  pendingDraft: PendingDraft | null;
  onPost: () => void;
  onCancel: () => void;
}) {
  const isUser = message.role === "user";

  if (isUser) {
    return (
      <div className="flex justify-end mb-4">
        <div className="max-w-[70%] rounded-2xl rounded-tr-sm bg-primary px-4 py-2.5 text-sm text-primary-foreground shadow-sm">
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start mb-4">
      <div className="max-w-[80%]">
        <div className="flex items-start gap-2">
          <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10">
            <Sparkles className="h-3.5 w-3.5 text-primary" />
          </div>
          <div className="rounded-2xl rounded-tl-sm bg-muted px-4 py-2.5 shadow-sm">
            {message.content === "" && message.isStreaming ? (
              <span className="flex items-center gap-1 text-sm text-muted-foreground">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                <span>Thinking...</span>
              </span>
            ) : (
              <p
                className="text-sm leading-relaxed"
                dangerouslySetInnerHTML={{
                  __html: renderInlineMarkdown(message.content) +
                    (message.isStreaming ? '<span class="animate-pulse ml-0.5">▋</span>' : ""),
                }}
              />
            )}

            {message.toolCalls && message.toolCalls.length > 0 && (
              <div className="mt-2 space-y-1">
                {message.toolCalls.map((tc, i) => (
                  <ToolCallChip key={i} toolCall={tc} />
                ))}
              </div>
            )}

            {pendingDraft && !message.isStreaming && (
              <ConfirmationCard
                draft={pendingDraft}
                onPost={onPost}
                onCancel={onCancel}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

const SUGGESTED_PROMPTS = [
  "What is my current cash balance?",
  "Show me the trial balance",
  "What invoices are overdue?",
  "Draft a journal entry for rent expense of $2,000",
];

// ── Main page ─────────────────────────────────────────────────────────────────

export default function AssistantPage() {
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [conversations, setConversations] = useState<AiConversation[]>([]);
  const [pendingDraft, setPendingDraft] = useState<PendingDraft | null>(null);

  const [attachedFile, setAttachedFile] = useState<File | null>(null);
  const [attachedPreview, setAttachedPreview] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Load conversation list on mount
  useEffect(() => {
    aiApi.listConversations().then(setConversations).catch(() => {
      // Sidebar is non-critical; swallow errors silently
    });
  }, []);

  // Auto-resize textarea
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    const maxH = parseInt(getComputedStyle(el).lineHeight ?? "20") * 5;
    el.style.height = `${Math.min(el.scrollHeight, maxH)}px`;
  }, [input]);

  const reloadConversations = useCallback(() => {
    aiApi.listConversations().then(setConversations).catch(() => {});
  }, []);

  async function loadConversation(id: string) {
    try {
      const msgs = await aiApi.getMessages(id);
      setConversationId(id);
      setPendingDraft(null);
      setMessages(
        msgs
          .filter((m) => m.role === "user" || m.role === "assistant")
          .map((m) => ({
            id: m.id,
            role: m.role as "user" | "assistant",
            content: m.content ?? "",
            ...(m.tool_calls ? { toolCalls: m.tool_calls as ToolCallDisplay[] } : {}),
          }))
      );
    } catch {
      // ignore load error
    }
  }

  function startNewChat() {
    setConversationId(null);
    setMessages([]);
    setPendingDraft(null);
    setInput("");
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setAttachedFile(file);
    const reader = new FileReader();
    reader.onload = (ev) => setAttachedPreview(ev.target?.result as string);
    reader.readAsDataURL(file);
    // Reset input so the same file can be re-selected
    e.target.value = "";
  }

  function clearAttachment() {
    setAttachedFile(null);
    setAttachedPreview(null);
  }

  async function sendMessage(text: string, confirmedDraftId?: string) {
    if (!text.trim() || isStreaming) return;

    // If there's an attachment, prefix the message with receipt context
    const effectiveText = attachedFile
      ? `Please analyse this receipt: ${attachedFile.name}\n\n${text}`
      : text;
    clearAttachment();

    const userMsg: ChatMessage = { id: uid(), role: "user", content: effectiveText };
    const assistantMsgId = uid();
    const assistantMsg: ChatMessage = {
      id: assistantMsgId,
      role: "assistant",
      content: "",
      toolCalls: [],
      isStreaming: true,
    };

    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    setIsStreaming(true);
    setInput("");

    const body = {
      message: effectiveText,
      ...(conversationId !== null ? { conversation_id: conversationId } : {}),
      ...(confirmedDraftId !== undefined ? { confirmed_draft_id: confirmedDraftId } : {}),
    };

    try {
      const res = await streamChat(body);

      if (!res.body) {
        throw new Error("No response body");
      }

      const reader = res.body.getReader() as ReadableStreamDefaultReader<Uint8Array>;
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const raw = line.slice(6).trim();
          if (!raw || raw === "[DONE]") continue;

          let event: Record<string, unknown>;
          try {
            event = JSON.parse(raw) as Record<string, unknown>;
          } catch {
            continue;
          }

          const type = event["type"] as string | undefined;

          if (type === "text") {
            const delta = (event["delta"] as string | undefined) ?? "";
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMsgId ? { ...m, content: m.content + delta } : m
              )
            );
          } else if (type === "conversation_id") {
            const cid = event["conversation_id"] as string | undefined;
            if (cid) setConversationId(cid);
          } else if (type === "tool_call") {
            const tc: ToolCallDisplay = {
              name: (event["name"] as string | undefined) ?? "tool",
              result: event["result"],
            };
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMsgId
                  ? { ...m, toolCalls: [...(m.toolCalls ?? []), tc] }
                  : m
              )
            );
          } else if (type === "confirmation_required") {
            const draft = event["draft"] as PendingDraft | undefined;
            if (draft) setPendingDraft(draft);
          } else if (type === "done") {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMsgId ? { ...m, isStreaming: false } : m
              )
            );
            setIsStreaming(false);
            reloadConversations();
          } else if (type === "error") {
            const errMsg = (event["message"] as string | undefined) ?? "An error occurred.";
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMsgId
                  ? { ...m, content: `Error: ${errMsg}`, isStreaming: false }
                  : m
              )
            );
            setIsStreaming(false);
          }
        }
      }
    } catch (err) {
      const errText = err instanceof Error ? err.message : "Failed to connect to AI assistant.";
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantMsgId
            ? { ...m, content: `Error: ${errText}`, isStreaming: false }
            : m
        )
      );
    } finally {
      setIsStreaming(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void sendMessage(input);
    }
  }

  function handlePost() {
    if (!pendingDraft) return;
    const draftId = pendingDraft.draftId;
    setPendingDraft(null);
    void sendMessage("Post the journal entry", draftId);
  }

  function handleCancel() {
    setPendingDraft(null);
    void sendMessage("Cancel the journal entry");
  }

  // The last assistant message is the one that holds pendingDraft UI
  const lastAssistantIdx = messages.reduceRight(
    (found, m, i) => (found === -1 && m.role === "assistant" ? i : found),
    -1
  );

  return (
    <div className="flex h-[calc(100vh-3.5rem)] overflow-hidden">
      {/* Sidebar */}
      <aside className="hidden md:flex w-64 flex-shrink-0 flex-col border-r bg-card">
        <div className="p-3 border-b">
          <button
            onClick={startNewChat}
            className="flex w-full items-center justify-center gap-2 rounded-md border border-primary/30 bg-primary/5 px-3 py-2 text-sm font-medium text-primary hover:bg-primary/10 transition-colors"
          >
            <Plus className="h-4 w-4" />
            New Chat
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-2 space-y-0.5">
          {conversations.length === 0 ? (
            <p className="px-3 py-4 text-center text-xs text-muted-foreground">
              No conversations yet
            </p>
          ) : (
            conversations.map((conv) => (
              <button
                key={conv.id}
                onClick={() => void loadConversation(conv.id)}
                className={
                  "w-full rounded-md px-3 py-2 text-left transition-colors " +
                  (conv.id === conversationId
                    ? "bg-primary/10 text-primary"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground")
                }
              >
                <p className="truncate text-sm font-medium">{conv.title}</p>
                <p className="text-xs opacity-70">{formatDate(conv.created_at)}</p>
              </button>
            ))
          )}
        </div>
      </aside>

      {/* Chat area */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 py-6 md:px-8">
          {messages.length === 0 ? (
            /* Empty state with suggested prompts */
            <div className="flex h-full flex-col items-center justify-center gap-6">
              <div className="text-center">
                <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-primary/10">
                  <Sparkles className="h-6 w-6 text-primary" />
                </div>
                <h2 className="text-xl font-semibold">AI Assistant</h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  Ask about your finances or request a journal entry
                </p>
              </div>

              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 w-full max-w-xl">
                {SUGGESTED_PROMPTS.map((prompt) => (
                  <button
                    key={prompt}
                    onClick={() => void sendMessage(prompt)}
                    className="rounded-xl border bg-card px-4 py-3 text-left text-sm text-foreground hover:bg-muted transition-colors shadow-sm"
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="mx-auto max-w-3xl">
              {messages.map((message, idx) => (
                <MessageBubble
                  key={message.id}
                  message={message}
                  pendingDraft={idx === lastAssistantIdx ? pendingDraft : null}
                  onPost={handlePost}
                  onCancel={handleCancel}
                />
              ))}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* Input area */}
        <div className="border-t bg-card px-4 py-3 md:px-8">
          <div className="mx-auto max-w-3xl">
            {/* Attachment preview */}
            {attachedPreview && attachedFile && (
              <div className="mb-2 flex items-center gap-2">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={attachedPreview}
                  alt={attachedFile.name}
                  className="h-16 w-16 rounded-md object-cover border"
                />
                <div className="flex-1 min-w-0">
                  <p className="truncate text-xs font-medium text-foreground">{attachedFile.name}</p>
                  <p className="text-xs text-muted-foreground">Image attached</p>
                </div>
                <button
                  onClick={clearAttachment}
                  className="rounded-full p-1 hover:bg-muted transition-colors"
                  aria-label="Remove attachment"
                >
                  <X className="h-4 w-4 text-muted-foreground" />
                </button>
              </div>
            )}

            {/* Hidden file input */}
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={handleFileChange}
            />

            <div className="flex items-end gap-2 rounded-xl border bg-background px-3 py-2 shadow-sm focus-within:ring-2 focus-within:ring-primary/30 transition-all">
              {/* Attachment button */}
              <button
                onClick={() => fileInputRef.current?.click()}
                disabled={isStreaming}
                className="mb-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-40 disabled:cursor-not-allowed"
                aria-label="Attach image"
                title="Attach receipt image"
              >
                <Paperclip className="h-4 w-4" />
              </button>

              <textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={isStreaming}
                rows={1}
                placeholder="Ask about your finances or request a journal entry..."
                className="flex-1 resize-none bg-transparent text-sm outline-none placeholder:text-muted-foreground disabled:cursor-not-allowed"
                style={{ maxHeight: "7.5rem" }}
              />
              <button
                onClick={() => void sendMessage(input)}
                disabled={isStreaming || !input.trim()}
                className="mb-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-40 disabled:cursor-not-allowed"
                aria-label="Send message"
              >
                {isStreaming ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Send className="h-4 w-4" />
                )}
              </button>
            </div>
            <p className="mt-1.5 text-center text-xs text-muted-foreground">
              Press Enter to send · Shift+Enter for new line
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
