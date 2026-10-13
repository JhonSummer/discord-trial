// Mesh hop unit: TTL budget + content-addressed msg_id (SHA-256 of the payload).
import { sha256 } from '@noble/hashes/sha2';

import { concatBytes, pack, unpack } from './wire';

export const MSG_ID_LEN = 16;
export const DEFAULT_TTL = 7;

export class Frame {
  constructor(public readonly ttl: number, public readonly payload: Uint8Array) {}

  get msgId(): Uint8Array {
    return sha256(this.payload).slice(0, MSG_ID_LEN);
  }

  get alive(): boolean {
    return this.ttl > 0;
  }

  hop(): Frame {
    return new Frame(this.ttl - 1, this.payload);
  }

  toBytes(): Uint8Array {
    const ttl = Math.max(0, Math.min(this.ttl, 0xff));
    return concatBytes(Uint8Array.of(0xf1, ttl), pack(this.payload));
  }

  static fromBytes(buf: Uint8Array): Frame {
    if (buf[0] !== 0xf1) throw new Error('unknown frame version');
    const [payload] = unpack(buf, 2);
    return new Frame(buf[1], payload);
  }
}
