// The app's conversation view-model: turns typed text into signed, end-to-end-encrypted envelopes
// on the shared wire format and carries them over any Transport (relay, BLE mesh, or loopback).
// Signatures (Ed25519), AEAD (ChaCha20-Poly1305), and the Envelope/Frame wire format are the real
// shared implementations. The room key is derived from a static X25519 ECDH as a PLACEHOLDER — the
// Double Ratchet / MLS TypeScript port (packages/crypto) will replace it with forward secrecy;
// everything else here is already production-shaped.
import { bytesToHex, utf8ToBytes } from '@noble/hashes/utils';

import { DEFAULT_TTL, Envelope, Frame, Snowflake, concatBytes } from '@messenger/protocol';
import { IdentityKeyPair, NONCE_LEN, PublicIdentity, aeadDecrypt, aeadEncrypt, hkdf } from '@messenger/crypto';

import { Transport } from '../transport/types';

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
  private readonly roomKey: Uint8Array;
  private readonly unsubscribe: () => void;

  constructor(
    private readonly me: IdentityKeyPair,
    private readonly peer: PublicIdentity,
    private readonly room: Uint8Array,
    private readonly transport: Transport,
    nodeId: number,
  ) {
    this.snowflake = new Snowflake(nodeId);
    this.roomKey = hkdf(me.dh(peer.agreementPub), 32, room, utf8ToBytes('room-key/v0'));
    this.unsubscribe = transport.subscribe((frame) => this.ingest(frame));
  }

  send(text: string): ChatMessage {
    const { nonce, ciphertext } = aeadEncrypt(this.roomKey, utf8ToBytes(text), this.room);
    const env = new Envelope(
      this.snowflake.next(),
      this.room,
      this.me.public.fingerprint,
      [],
      0n,
      concatBytes(nonce, ciphertext),
    );
    env.sig = this.me.sign(env.body());
    this.transport.send(new Frame(DEFAULT_TTL, env.toBytes()).toBytes());

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

  private ingest(frameBytes: Uint8Array): void {
    let env: Envelope;
    try {
      env = Envelope.fromBytes(Frame.fromBytes(frameBytes).payload);
    } catch {
      return; // not a well-formed frame/envelope — ignore
    }
    if (bytesToHex(env.sender) === bytesToHex(this.me.public.fingerprint)) return; // our own traffic

    const fromPeer = bytesToHex(env.sender) === bytesToHex(this.peer.fingerprint);
    if (!fromPeer || !this.peer.verify(env.sig, env.body())) return; // drop unauthenticated traffic

    const nonce = env.ciphertext.slice(0, NONCE_LEN);
    const ciphertext = env.ciphertext.slice(NONCE_LEN);
    const text = decoder.decode(aeadDecrypt(this.roomKey, nonce, ciphertext, this.room));
    this.messages.push({
      eid: env.eid,
      senderFingerprint: bytesToHex(env.sender),
      text,
      mine: false,
      verified: true,
    });
  }
}
