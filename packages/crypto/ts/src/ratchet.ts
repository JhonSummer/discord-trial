// Double Ratchet (Signal) on X25519 + HKDF + ChaCha20-Poly1305 — a faithful port of the Python
// reference (crypto/cryptocore/ratchet.py). Per-message forward secrecy and
// post-compromise security, with bounded skipped/out-of-order handling. The key schedule (HKDF
// root KDF, HMAC chain KDF, header layout, AEAD AD binding) is byte-identical to Python, which the
// cross-language conformance vectors lock down. Reference prototype — production should use libsignal.
import { x25519 } from '@noble/curves/ed25519';
import { bytesToHex, concatBytes, randomBytes, utf8ToBytes } from '@noble/hashes/utils';

import { aeadDecrypt, aeadEncrypt, hkdf, hmacSha256, NONCE_LEN } from './primitives';

export const MAX_SKIP = 1000;

export class RatchetError extends Error {}

const RK_INFO = utf8ToBytes('DoubleRatchet/rk');

function dh(priv: Uint8Array, pub: Uint8Array): Uint8Array {
  return x25519.getSharedSecret(priv, pub);
}

function kdfRk(rk: Uint8Array, dhOut: Uint8Array): [Uint8Array, Uint8Array] {
  const out = hkdf(dhOut, 64, rk, RK_INFO);
  return [out.slice(0, 32), out.slice(32)];
}

function kdfCk(ck: Uint8Array): [Uint8Array, Uint8Array] {
  return [hmacSha256(ck, Uint8Array.of(0x02)), hmacSha256(ck, Uint8Array.of(0x01))]; // [next_ck, message_key]
}

function u32(n: number): Uint8Array {
  const b = new Uint8Array(4);
  new DataView(b.buffer).setUint32(0, n, false);
  return b;
}

export class Header {
  constructor(public readonly dh: Uint8Array, public readonly pn: number, public readonly n: number) {}

  serialize(): Uint8Array {
    return concatBytes(this.dh, u32(this.pn), u32(this.n));
  }

  static deserialize(data: Uint8Array): Header {
    const v = new DataView(data.buffer, data.byteOffset, data.byteLength);
    return new Header(data.slice(0, 32), v.getUint32(32, false), v.getUint32(36, false));
  }
}

export class DoubleRatchet {
  private DHs: Uint8Array | null = null; // our current ratchet private scalar
  private DHr: Uint8Array | null = null; // their current ratchet public key
  private RK: Uint8Array = new Uint8Array(0);
  private CKs: Uint8Array | null = null;
  private CKr: Uint8Array | null = null;
  private Ns = 0;
  private Nr = 0;
  private PN = 0;
  private readonly skipped = new Map<string, Uint8Array>();

  get ratchetPublic(): Uint8Array {
    if (this.DHs === null) throw new RatchetError('no ratchet key');
    return x25519.getPublicKey(this.DHs);
  }

  static initAlice(rootKey: Uint8Array, bobRatchetPub: Uint8Array): DoubleRatchet {
    const self = new DoubleRatchet();
    self.DHs = randomBytes(32);
    self.DHr = bobRatchetPub;
    [self.RK, self.CKs] = kdfRk(rootKey, dh(self.DHs, self.DHr));
    return self;
  }

  static initBob(rootKey: Uint8Array, bobRatchetPriv: Uint8Array): DoubleRatchet {
    const self = new DoubleRatchet();
    self.DHs = bobRatchetPriv;
    self.RK = rootKey;
    return self;
  }

  encrypt(plaintext: Uint8Array, associatedData: Uint8Array = new Uint8Array(0)): [Header, Uint8Array] {
    if (this.CKs === null) throw new RatchetError('no sending chain yet (Bob must receive first)');
    const [nextCk, mk] = kdfCk(this.CKs);
    this.CKs = nextCk;
    const header = new Header(this.ratchetPublic, this.PN, this.Ns);
    this.Ns += 1;
    const { nonce, ciphertext } = aeadEncrypt(mk, plaintext, concatBytes(associatedData, header.serialize()));
    return [header, concatBytes(nonce, ciphertext)];
  }

  decrypt(header: Header, body: Uint8Array, associatedData: Uint8Array = new Uint8Array(0)): Uint8Array {
    const nonce = body.slice(0, NONCE_LEN);
    const ciphertext = body.slice(NONCE_LEN);
    const ad = concatBytes(associatedData, header.serialize());

    const skippedKey = `${bytesToHex(header.dh)}:${header.n}`;
    const skippedMk = this.skipped.get(skippedKey);
    if (skippedMk !== undefined) {
      this.skipped.delete(skippedKey);
      return aeadDecrypt(skippedMk, nonce, ciphertext, ad);
    }

    if (this.DHr === null || bytesToHex(header.dh) !== bytesToHex(this.DHr)) {
      this.skip(header.pn);
      this.dhRatchet(header);
    }
    this.skip(header.n);

    const [nextCk, mk] = kdfCk(this.CKr as Uint8Array);
    this.CKr = nextCk;
    this.Nr += 1;
    return aeadDecrypt(mk, nonce, ciphertext, ad);
  }

  private skip(until: number): void {
    if (this.Nr + MAX_SKIP < until) throw new RatchetError('too many skipped messages');
    if (this.CKr !== null) {
      while (this.Nr < until) {
        const [nextCk, mk] = kdfCk(this.CKr);
        this.CKr = nextCk;
        this.skipped.set(`${bytesToHex(this.DHr as Uint8Array)}:${this.Nr}`, mk);
        this.Nr += 1;
      }
    }
  }

  private dhRatchet(header: Header): void {
    this.PN = this.Ns;
    this.Ns = 0;
    this.Nr = 0;
    this.DHr = header.dh;
    [this.RK, this.CKr] = kdfRk(this.RK, dh(this.DHs as Uint8Array, this.DHr));
    this.DHs = randomBytes(32);
    [this.RK, this.CKs] = kdfRk(this.RK, dh(this.DHs, this.DHr));
  }
}

// Exposed for the cross-language conformance vectors (the key schedule must match Python exactly).
export { kdfRk, kdfCk };
