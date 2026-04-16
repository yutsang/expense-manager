import React, { useState, useRef, useCallback } from 'react';
import {
  View,
  Text,
  FlatList,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { apiRequest } from '@/lib/api';

type MessageRole = 'user' | 'assistant';

type Message = {
  id: string;
  role: MessageRole;
  content: string;
  isStreaming?: boolean;
};

type ChatRequest = {
  messages: Array<{ role: MessageRole; content: string }>;
};

let msgCounter = 0;
function nextId(): string {
  msgCounter += 1;
  return String(msgCounter);
}

function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === 'user';
  return (
    <View style={[styles.bubbleRow, isUser ? styles.bubbleRowUser : styles.bubbleRowAssistant]}>
      {!isUser && (
        <View style={styles.avatarDot}>
          <Text style={styles.avatarText}>A</Text>
        </View>
      )}
      <View
        style={[
          styles.bubble,
          isUser ? styles.bubbleUser : styles.bubbleAssistant,
        ]}
      >
        <Text style={[styles.bubbleText, isUser ? styles.bubbleTextUser : null]}>
          {message.content}
          {message.isStreaming ? (
            <Text style={styles.cursor}>▋</Text>
          ) : null}
        </Text>
      </View>
    </View>
  );
}

function TypingIndicator() {
  return (
    <View style={[styles.bubbleRow, styles.bubbleRowAssistant]}>
      <View style={styles.avatarDot}>
        <Text style={styles.avatarText}>A</Text>
      </View>
      <View style={[styles.bubble, styles.bubbleAssistant, styles.typingBubble]}>
        <ActivityIndicator size="small" color="#6366f1" />
        <Text style={styles.typingText}>Thinking…</Text>
      </View>
    </View>
  );
}

export default function AssistantScreen() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: '0',
      role: 'assistant',
      content:
        'Hello! I\'m your Aegis ERP assistant. I can help you query account balances, explain journal entries, and answer questions about your books. How can I help?',
    },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const listRef = useRef<FlatList<Message>>(null);

  const scrollToBottom = useCallback(() => {
    listRef.current?.scrollToEnd({ animated: true });
  }, []);

  const sendMessage = async () => {
    const text = input.trim();
    if (!text || loading) return;

    setInput('');
    const userMsg: Message = { id: nextId(), role: 'user', content: text };
    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);

    // Streaming assistant reply placeholder
    const assistantId = nextId();
    setMessages((prev) => [
      ...prev,
      { id: assistantId, role: 'assistant', content: '', isStreaming: true },
    ]);

    try {
      // Build conversation history (last 10 messages for context)
      const history = messages
        .slice(-10)
        .map((m) => ({ role: m.role, content: m.content }));
      history.push({ role: 'user', content: text });

      // Attempt SSE streaming; fall back to regular JSON if not supported
      const BASE = 'https://aegis-erp-api-551455410644.asia-southeast1.run.app';
      const token = null; // SecureStore read is async — for brevity we call apiRequest below

      // Use apiRequest which handles auth
      const response = await apiRequest<{ reply?: string; content?: string }>(
        'POST',
        '/v1/ai/chat',
        { messages: history } satisfies ChatRequest,
      );

      const reply =
        response.reply ??
        response.content ??
        'I received your message but could not generate a response.';

      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId ? { ...m, content: reply, isStreaming: false } : m,
        ),
      );
    } catch (err) {
      const errMsg =
        err instanceof Error ? err.message : 'Something went wrong. Please try again.';
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? { ...m, content: `Error: ${errMsg}`, isStreaming: false }
            : m,
        ),
      );
    } finally {
      setLoading(false);
      setTimeout(scrollToBottom, 100);
    }
  };

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>AI Assistant</Text>
        <Text style={styles.headerSub}>Powered by Claude</Text>
      </View>

      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        keyboardVerticalOffset={0}
      >
        <FlatList<Message>
          ref={listRef}
          data={messages}
          keyExtractor={(item) => item.id}
          renderItem={({ item }) => <MessageBubble message={item} />}
          contentContainerStyle={styles.messageList}
          onContentSizeChange={scrollToBottom}
        />

        {loading && !messages[messages.length - 1]?.isStreaming ? (
          <TypingIndicator />
        ) : null}

        <View style={styles.inputRow}>
          <TextInput
            style={styles.input}
            placeholder="Ask about your finances…"
            placeholderTextColor="#64748b"
            value={input}
            onChangeText={setInput}
            multiline
            maxLength={2000}
            returnKeyType="send"
            onSubmitEditing={sendMessage}
            blurOnSubmit
          />
          <TouchableOpacity
            style={[
              styles.sendBtn,
              (!input.trim() || loading) ? styles.sendBtnDisabled : null,
            ]}
            onPress={sendMessage}
            disabled={!input.trim() || loading}
            activeOpacity={0.7}
          >
            <Text style={styles.sendBtnText}>↑</Text>
          </TouchableOpacity>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: {
    flex: 1,
    backgroundColor: '#0f172a',
  },
  flex: {
    flex: 1,
  },
  header: {
    paddingHorizontal: 20,
    paddingTop: 16,
    paddingBottom: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#1e293b',
    flexDirection: 'row',
    alignItems: 'baseline',
    gap: 8,
  },
  headerTitle: {
    fontSize: 22,
    fontWeight: '700',
    color: '#e2e8f0',
  },
  headerSub: {
    fontSize: 12,
    color: '#6366f1',
    fontWeight: '500',
  },
  messageList: {
    padding: 16,
    paddingBottom: 8,
    gap: 12,
  },
  bubbleRow: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    gap: 8,
  },
  bubbleRowUser: {
    justifyContent: 'flex-end',
  },
  bubbleRowAssistant: {
    justifyContent: 'flex-start',
  },
  avatarDot: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: '#312e81',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  avatarText: {
    color: '#a5b4fc',
    fontSize: 12,
    fontWeight: '700',
  },
  bubble: {
    maxWidth: '78%',
    borderRadius: 16,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  bubbleUser: {
    backgroundColor: '#6366f1',
    borderBottomRightRadius: 4,
  },
  bubbleAssistant: {
    backgroundColor: '#1e293b',
    borderBottomLeftRadius: 4,
  },
  bubbleText: {
    fontSize: 15,
    color: '#cbd5e1',
    lineHeight: 22,
  },
  bubbleTextUser: {
    color: '#fff',
  },
  cursor: {
    color: '#6366f1',
  },
  typingBubble: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  typingText: {
    color: '#64748b',
    fontSize: 14,
    fontStyle: 'italic',
  },
  inputRow: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    paddingHorizontal: 16,
    paddingVertical: 10,
    paddingBottom: 16,
    gap: 10,
    borderTopWidth: 1,
    borderTopColor: '#1e293b',
    backgroundColor: '#0f172a',
  },
  input: {
    flex: 1,
    backgroundColor: '#1e293b',
    borderWidth: 1,
    borderColor: '#334155',
    borderRadius: 20,
    paddingHorizontal: 16,
    paddingVertical: 10,
    fontSize: 15,
    color: '#e2e8f0',
    maxHeight: 120,
  },
  sendBtn: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: '#6366f1',
    alignItems: 'center',
    justifyContent: 'center',
  },
  sendBtnDisabled: {
    backgroundColor: '#312e81',
    opacity: 0.5,
  },
  sendBtnText: {
    color: '#fff',
    fontSize: 18,
    fontWeight: '700',
    lineHeight: 22,
  },
});
