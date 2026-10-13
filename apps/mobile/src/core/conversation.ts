// The app's conversation view-model: turns typed text into signed, end-to-end-encrypted envelopes
// on the shared wire format and carries them over any Transport (relay, BLE mesh, or loopback).
// Encryption is the real Signal Double Ratchet (forward secrecy + post-compromise security);
// messages are signed with Ed25519 and ride the shared Envelope/Frame wire format. The ratchet is
// bootstrapped by src/core/session.ts (from the handshake in production; from the known identities
// in the single-device demo). Relays only ever see opaque ciphertext.
import { bytesToHex, concatBytes, utf8ToBytes } from '@noble/hashes/utils';

import { Envelope, Snowflake } from '@messenger/protocol';
import { DoubleRatchet, Header, IdentityKeyPair, PublicIdentity } from '@messenger/crypto';

import { Transport } from '../transport/types';

// Ratchet header on the wire: 32-byte ratchet public key + 4-byte PN + 4-byte N.
const RATCHET_HEADER_LEN = 40;

export interface ChatMessage {
  eid: bigint;
  senderFingerprint: string;
  text: string;
  mine: boolean;
  verified: boolean;
}

const decoder = new TextDecoder();

export class Conversation {
  readonly messages: ChatMessage[] = [];
  private readonly snowflake: Snowflake;
  private readonly unsubscribe: () => void;

  constructor(
    private readonly me: IdentityKeyPair,
    private readonly peer: PublicIdentity,
    private readonly room: Uint8Array,
    private readonly transport: Transport,
    private readonly ratchet: DoubleRatchet,
    nodeId: number,
  ) {
    this.snowflake = new Snowflake(nodeId);
    this.unsubscribe = transport.subscribe((frame) => this.ingest(frame));
  }

  send(text: string): ChatMessage {
    const [header, body] = this.ratchet.encrypt(utf8ToBytes(text), this.room);
    const env = new Envelope(
      this.snowflake.next(),
      this.room,
      this.me.public.fingerprint,
      [],
      0n,
      concatBytes(header.serialize(), body),
    );
    env.sig = this.me.sign(env.body());
    // The Conversation deals in envelopes; the mesh Transport owns hop framing (TTL/dedup).
    this.transport.send(env.toBytes());

    const msg: ChatMessage = {
      eid: env.eid,
      senderFingerprint: bytesToHex(this.me.public.fingerprint),
      text,
      mine: true,
      verified: true,
    };
    this.messages.push(msg);
    return msg;
  }

  close(): void {
    this.unsubscribe();
  }

  private ingest(envelopeBytes: Uint8Array): void {
    let env: Envelope;
    try {
      env = Envelope.fromBytes(envelopeBytes);
    } catch {
      return; // not a well-formed envelope — ignore
    }
    if (bytesToHex(env.sender) === bytesToHex(this.me.public.fingerprint)) return; // our own traffic

    const fromPeer = bytesToHex(env.sender) === bytesToHex(this.peer.fingerprint);
    if (!fromPeer || !this.peer.verify(env.sig, env.body())) return; // drop unauthenticated traffic

    let text: string;
    try {
      const header = Header.deserialize(env.ciphertext.slice(0, RATCHET_HEADER_LEN));
      const body = env.ciphertext.slice(RATCHET_HEADER_LEN);
      text = decoder.decode(this.ratchet.decrypt(header, body, this.room));
    } catch {
      return; // undecryptable (replay, corruption, or out-of-session) — drop
    }
    this.messages.push({
      eid: env.eid,
      senderFingerprint: bytesToHex(env.sender),
      text,
      mine: false,
      verified: true,
    });
  }
}
