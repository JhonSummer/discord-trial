// Identity keys (Ed25519 signing + X25519 agreement), fingerprints, and Signal-style safety
// numbers — matching the Python reference (Ed25519 signatures are deterministic, so they agree).
import { ed25519, x25519 } from '@noble/curves/ed25519';
import { concatBytes, randomBytes, utf8ToBytes } from '@noble/hashes/utils';

import { sha256 } from './primitives';

function compareBytes(a: Uint8Array, b: Uint8Array): number {
  const n = Math.min(a.length, b.length);
  for (let i = 0; i < n; i++) {
    if (a[i] !== b[i]) return a[i] < b[i] ? -1 : 1;
  }
  return a.length - b.length;
}

export class PublicIdentity {
  constructor(public readonly signingPub: Uint8Array, public readonly agreementPub: Uint8Array) {
    if (signingPub.length !== 32 || agreementPub.length !== 32) {
      throw new Error('public keys must be 32 raw bytes each');
    }
  }

  get fingerprint(): Uint8Array {
    return sha256(utf8ToBytes('idfp'), this.signingPub, this.agreementPub);
  }

  verify(signature: Uint8Array, message: Uint8Array): boolean {
    try {
      return ed25519.verify(signature, message, this.signingPub);
    } catch {
      return false;
    }
  }

  serialize(): Uint8Array {
    return concatBytes(this.signingPub, this.agreementPub);
  }

  static deserialize(data: Uint8Array): PublicIdentity {
    if (data.length !== 64) throw new Error('serialized PublicIdentity must be 64 bytes');
    return new PublicIdentity(data.slice(0, 32), data.slice(32));
  }
}

export class IdentityKeyPair {
  constructor(private readonly signingPriv: Uint8Array, private readonly agreementPriv: Uint8Array) {}

  static generate(): IdentityKeyPair {
    return new IdentityKeyPair(randomBytes(32), randomBytes(32));
  }

  static fromSeeds(signingSeed: Uint8Array, agreementScalar: Uint8Array): IdentityKeyPair {
    return new IdentityKeyPair(signingSeed, agreementScalar);
  }

  get public(): PublicIdentity {
    return new PublicIdentity(ed25519.getPublicKey(this.signingPriv), x25519.getPublicKey(this.agreementPriv));
  }

  sign(message: Uint8Array): Uint8Array {
    return ed25519.sign(message, this.signingPriv);
  }

  dh(peerAgreementPub: Uint8Array): Uint8Array {
    return x25519.getSharedSecret(this.agreementPriv, peerAgreementPub);
  }
}

export function safetyNumber(a: PublicIdentity, b: PublicIdentity, digits = 60): string {
  const fa = a.fingerprint;
  const fb = b.fingerprint;
  const [lo, hi] = compareBytes(fa, fb) <= 0 ? [fa, fb] : [fb, fa];
  let acc = sha256(utf8ToBytes('safetynumber'), lo, hi);
  const out: string[] = [];
  while (out.length < digits) {
    acc = sha256(acc);
    for (const byte of acc) {
      out.push(String(byte % 10));
      if (out.length >= digits) break;
    }
  }
  const grouped = out.join('');
  const parts: string[] = [];
  for (let i = 0; i < digits; i += 5) parts.push(grouped.slice(i, i + 5));
  return parts.join(' ');
}
