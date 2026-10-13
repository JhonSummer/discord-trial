import React, { useState } from 'react';
import {
  FlatList,
  KeyboardAvoidingView,
  ListRenderItemInfo,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import { ChatMessage } from '../core/conversation';
import { useConversation } from './useConversation';

const colors = {
  bg: '#0b0f14',
  surface: '#161c26',
  mine: '#2f6df6',
  text: '#e8edf4',
  muted: '#8a97a8',
  line: '#232c39',
  ok: '#49c17c',
};

function Bubble({ message }: { message: ChatMessage }): React.JSX.Element {
  return (
    <View style={[styles.row, message.mine ? styles.rowMine : styles.rowPeer]}>
      <View style={[styles.bubble, message.mine ? styles.bubbleMine : styles.bubblePeer]}>
        <Text style={styles.bubbleText}>{message.text}</Text>
        {!message.mine && (
          <Text style={styles.meta}>{message.verified ? 'verified · encrypted' : 'unverified'}</Text>
        )}
      </View>
    </View>
  );
}

export function ChatScreen(): React.JSX.Element {
  const { messages, send, myFingerprint, safetyNumber } = useConversation();
  const [draft, setDraft] = useState('');

  const onSend = () => {
    send(draft);
    setDraft('');
  };

  return (
    <KeyboardAvoidingView
      style={styles.screen}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <View style={styles.header}>
        <Text style={styles.title}>Mesh Messenger</Text>
        <Text style={styles.subtitle}>end-to-end encrypted · loopback demo</Text>
        <Text style={styles.safety} numberOfLines={2}>
          safety № {safetyNumber}
        </Text>
        <Text style={styles.fingerprint}>you: {myFingerprint}…</Text>
      </View>

      <FlatList
        data={messages}
        keyExtractor={(m) => m.eid.toString()}
        renderItem={({ item }: ListRenderItemInfo<ChatMessage>) => <Bubble message={item} />}
        contentContainerStyle={styles.list}
        ListEmptyComponent={
          <Text style={styles.empty}>Send a message — the demo peer echoes it back, signed and encrypted.</Text>
        }
      />

      <View style={styles.composer}>
        <TextInput
          style={styles.input}
          value={draft}
          onChangeText={setDraft}
          placeholder="Message"
          placeholderTextColor={colors.muted}
          onSubmitEditing={onSend}
          returnKeyType="send"
        />
        <Pressable style={styles.sendBtn} onPress={onSend} accessibilityRole="button">
          <Text style={styles.sendText}>Send</Text>
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  header: {
    paddingTop: 56,
    paddingHorizontal: 20,
    paddingBottom: 14,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.line,
  },
  title: { color: colors.text, fontSize: 22, fontWeight: '700' },
  subtitle: { color: colors.muted, fontSize: 13, marginTop: 2 },
  safety: { color: colors.muted, fontSize: 11, marginTop: 10, fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace' },
  fingerprint: { color: colors.muted, fontSize: 11, marginTop: 2, fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace' },
  list: { padding: 14, flexGrow: 1 },
  empty: { color: colors.muted, textAlign: 'center', marginTop: 40, paddingHorizontal: 30, lineHeight: 20 },
  row: { marginVertical: 4, flexDirection: 'row' },
  rowMine: { justifyContent: 'flex-end' },
  rowPeer: { justifyContent: 'flex-start' },
  bubble: { maxWidth: '80%', paddingVertical: 9, paddingHorizontal: 13, borderRadius: 16 },
  bubbleMine: { backgroundColor: colors.mine, borderBottomRightRadius: 4 },
  bubblePeer: { backgroundColor: colors.surface, borderBottomLeftRadius: 4 },
  bubbleText: { color: colors.text, fontSize: 15 },
  meta: { color: colors.ok, fontSize: 10, marginTop: 4 },
  composer: {
    flexDirection: 'row',
    padding: 10,
    gap: 8,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.line,
    backgroundColor: colors.bg,
  },
  input: {
    flex: 1,
    backgroundColor: colors.surface,
    color: colors.text,
    borderRadius: 20,
    paddingHorizontal: 16,
    paddingVertical: 10,
    fontSize: 15,
  },
  sendBtn: { backgroundColor: colors.mine, borderRadius: 20, paddingHorizontal: 18, justifyContent: 'center' },
  sendText: { color: '#fff', fontWeight: '600', fontSize: 15 },
});
