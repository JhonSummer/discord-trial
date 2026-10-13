// React bridge from the tested, transport-agnostic Conversation view-model (src/core) to UI state.
// For a single-device demo it wires "me" and an in-process echo "peer" to a LoopbackBus, so the
// full signed + end-to-end-encrypted round trip runs on one phone with no network. Swapping the
// LoopbackBus for the relay / BLE-mesh Transport is the only change needed to talk to real peers —
// the core code above this line does not change.
import { useCallback, useRef, useState } from 'react';

import { bytesToHex } from '@noble/hashes/utils';

import { IdentityKeyPair, safetyNumber } from '@messenger/crypto';

import { ChatMessage, Conversation } from '../core/conversation';
import { LoopbackBus } from '../transport/loopback';

const ROOM = new TextEncoder().encode('general');

interface Session {
  mine: Conversation;
  peer: Conversation;
  myFingerprint: string;
  safetyNumber: string;
}

function createSession(): Session {
  const me = IdentityKeyPair.generate();
  const peer = IdentityKeyPair.generate();
  const bus = new LoopbackBus();
  return {
    mine: new Conversation(me, peer.public, ROOM, bus.endpoint(), 1),
    peer: new Conversation(peer, me.public, ROOM, bus.endpoint(), 2),
    myFingerprint: bytesToHex(me.public.fingerprint).slice(0, 16),
    safetyNumber: safetyNumber(me.public, peer.public),
  };
}

export interface ConversationState {
  messages: ChatMessage[];
  myFingerprint: string;
  safetyNumber: string;
  send(text: string): void;
}

export function useConversation(): ConversationState {
  const sessionRef = useRef<Session | null>(null);
  if (sessionRef.current === null) sessionRef.current = createSession();
  const session = sessionRef.current;

  const [messages, setMessages] = useState<ChatMessage[]>([]);

  const send = useCallback(
    (text: string) => {
      const trimmed = text.trim();
      if (!trimmed) return;
      session.mine.send(trimmed);
      session.peer.send(trimmed); // demo echo peer, exercising verify + decrypt on our side
      setMessages([...session.mine.messages]);
    },
    [session],
  );

  return {
    messages,
    myFingerprint: session.myFingerprint,
    safetyNumber: session.safetyNumber,
    send,
  };
}
