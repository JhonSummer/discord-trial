import { x25519 } from '@noble/curves/ed25519';
import { utf8ToBytes } from '@noble/hashes/utils';

import { DoubleRatchet, RatchetError } from '../src';

const enc = (s: string) => utf8ToBytes(s);
const dec = (b: Uint8Array) => new TextDecoder().decode(b);

function session() {
  const rootKey = new Uint8Array(32).fill(7);
  const bobPriv = new Uint8Array(32).fill(3);
  const bobPub = x25519.getPublicKey(bobPriv);
  const alice = DoubleRatchet.initAlice(rootKey, bobPub);
  const bob = DoubleRatchet.initBob(rootKey, bobPriv);
  return { alice, bob };
}

test('alice and bob exchange messages, including a DH ratchet step', () => {
  const { alice, bob } = session();

  const [h1, b1] = alice.encrypt(enc('hello bob'));
  expect(dec(bob.decrypt(h1, b1))).toBe('hello bob');

  // Bob can now reply (his sending chain exists after receiving), forcing alice to DH-ratchet.
  const [h2, b2] = bob.encrypt(enc('hi alice'));
  expect(dec(alice.decrypt(h2, b2))).toBe('hi alice');

  const [h3, b3] = alice.encrypt(enc('how are you'));
  expect(dec(bob.decrypt(h3, b3))).toBe('how are you');
});

test('out-of-order delivery within a chain is handled via skipped keys', () => {
  const { alice, bob } = session();
  const m1 = alice.encrypt(enc('one'));
  const m2 = alice.encrypt(enc('two'));
  const m3 = alice.encrypt(enc('three'));

  // Deliver 3, then 1, then 2.
  expect(dec(bob.decrypt(m3[0], m3[1]))).toBe('three');
  expect(dec(bob.decrypt(m1[0], m1[1]))).toBe('one');
  expect(dec(bob.decrypt(m2[0], m2[1]))).toBe('two');
});

test('associated data is bound and tampering is rejected', () => {
  const { alice, bob } = session();
  const ad = enc('room:general');
  const [h, body] = alice.encrypt(enc('secret'), ad);

  expect(dec(bob.decrypt(h, body, ad))).toBe('secret');

  const { alice: alice2, bob: bob2 } = session();
  const [h2, body2] = alice2.encrypt(enc('secret'), ad);
  const tampered = Uint8Array.from(body2);
  tampered[tampered.length - 1] ^= 0x01;
  expect(() => bob2.decrypt(h2, tampered, ad)).toThrow();
});

test('exceeding the skip bound is rejected', () => {
  const { alice, bob } = session();
  // Advance alice far beyond MAX_SKIP without delivering, then deliver a high-n message.
  let last: [import('../src').Header, Uint8Array] | null = null;
  for (let i = 0; i < 1002; i++) last = alice.encrypt(enc(`m${i}`));
  expect(last).not.toBeNull();
  expect(() => bob.decrypt(last![0], last![1])).toThrow(RatchetError);
});
