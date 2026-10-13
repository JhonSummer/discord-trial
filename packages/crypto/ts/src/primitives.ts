// Thin wrappers over @noble so the app and the Python reference compute identical bytes.
import { chacha20poly1305 } from '@noble/ciphers/chacha';
import { hkdf as nobleHkdf } from '@noble/hashes/hkdf';
import { hmac as nobleHmac } from '@noble/hashes/hmac';
import { sha256 as nobleSha256 } from '@noble/hashes/sha2';
import { concatBytes, randomBytes } from '@noble/hashes/utils';

export const EMPTY = new Uint8Array(0);
export const NONCE_LEN = 12;

export function sha256(...chunks: Uint8Array[]): Uint8Array {
  return nobleSha256(concatBytes(...chunks));
}

export function hmacSha256(key: Uint8Array, data: Uint8Array): Uint8Array {
  return nobleHmac(nobleSha256, key, data);
}

export function hkdf(ikm: Uint8Array, length: number, salt: Uint8Array = EMPTY, info: Uint8Array = EMPTY): Uint8Array {
  return nobleHkdf(nobleSha256, ikm, salt, info, length);
}

export function aeadEncrypt(
  key: Uint8Array,
  plaintext: Uint8Array,
  associatedData: Uint8Array = EMPTY,
  nonce?: Uint8Array,
): { nonce: Uint8Array; ciphertext: Uint8Array } {
  const n = nonce ?? randomBytes(NONCE_LEN);
  const ciphertext = chacha20poly1305(key, n, associatedData).encrypt(plaintext);
  return { nonce: n, ciphertext };
}

export function aeadDecrypt(
  key: Uint8Array,
  nonce: Uint8Array,
  ciphertext: Uint8Array,
  associatedData: Uint8Array = EMPTY,
): Uint8Array {
  return chacha20poly1305(key, nonce, associatedData).decrypt(ciphertext);
}
