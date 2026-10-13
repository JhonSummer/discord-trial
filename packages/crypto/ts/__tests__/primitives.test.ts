import { aeadDecrypt, aeadEncrypt, hkdf, hmacSha256, sha256 } from '../src';
import { utf8ToBytes } from '@noble/hashes/utils';

test('sha256 concatenates its chunks like the Python reference', () => {
  const joined = sha256(utf8ToBytes('abc'), utf8ToBytes('def'));
  const whole = sha256(utf8ToBytes('abcdef'));
  expect([...joined]).toEqual([...whole]);
  expect(joined.length).toBe(32);
});

test('hmac and hkdf produce fixed-length output', () => {
  const key = utf8ToBytes('key');
  expect(hmacSha256(key, utf8ToBytes('data')).length).toBe(32);
  expect(hkdf(utf8ToBytes('ikm'), 64, utf8ToBytes('salt'), utf8ToBytes('info')).length).toBe(64);
});

test('aead roundtrips and rejects tampering', () => {
  const key = new Uint8Array(32).fill(9);
  const ad = utf8ToBytes('header');
  const pt = utf8ToBytes('secret message');

  const { nonce, ciphertext } = aeadEncrypt(key, pt, ad);
  expect([...aeadDecrypt(key, nonce, ciphertext, ad)]).toEqual([...pt]);

  const flipped = Uint8Array.from(ciphertext);
  flipped[0] ^= 0x01;
  expect(() => aeadDecrypt(key, nonce, flipped, ad)).toThrow();
  expect(() => aeadDecrypt(key, nonce, ciphertext, utf8ToBytes('wrong'))).toThrow();
});
