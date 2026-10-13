import { bytesToHex } from '@noble/hashes/utils';

import { IdentityKeyPair } from '@messenger/crypto';

import { Conversation } from '../src/core/conversation';
import { LoopbackBus } from '../src/transport/loopback';

const room = new TextEncoder().encode('general');
const seed = (start: number) => Uint8Array.from({ length: 32 }, (_, i) => start + i);
const pair = (signStart: number, agreeStart: number) =>
  IdentityKeyPair.fromSeeds(seed(signStart), seed(agreeStart));

test('two participants exchange signed, E2EE messages over a transport', () => {
  const alice = pair(0, 32);
  const bob = pair(64, 96);
  const bus = new LoopbackBus();
  const aliceConv = new Conversation(alice, bob.public, room, bus.endpoint(), 1);
  const bobConv = new Conversation(bob, alice.public, room, bus.endpoint(), 2);

  aliceConv.send('hello bob');
  bobConv.send('hi alice');

  expect(aliceConv.messages.map((m) => m.text)).toEqual(['hello bob', 'hi alice']);
  expect(bobConv.messages.map((m) => m.text)).toEqual(['hello bob', 'hi alice']);

  const received = bobConv.messages[0];
  expect(received.mine).toBe(false);
  expect(received.verified).toBe(true);
  expect(received.senderFingerprint).toBe(bytesToHex(alice.public.fingerprint));
});

test('a forged signature from an impostor is dropped', () => {
  const alice = pair(0, 32);
  const bob = pair(64, 96);
  const mallory = pair(128, 160);
  const bus = new LoopbackBus();
  // Bob expects to hear from alice, but mallory (a different identity) is on the bus.
  const bobConv = new Conversation(bob, alice.public, room, bus.endpoint(), 2);
  const malloryConv = new Conversation(mallory, bob.public, room, bus.endpoint(), 3);

  malloryConv.send('i am alice, send money');

  expect(bobConv.messages).toHaveLength(0);
});

test('relays on the transport see only opaque ciphertext', () => {
  const alice = pair(0, 32);
  const bob = pair(64, 96);
  const bus = new LoopbackBus();
  const seen: Uint8Array[] = [];
  bus.endpoint().subscribe((frame) => seen.push(frame)); // a passive relay / eavesdropper
  const aliceConv = new Conversation(alice, bob.public, room, bus.endpoint(), 1);

  aliceConv.send('topsecret');

  expect(seen).toHaveLength(1);
  const needle = bytesToHex(new TextEncoder().encode('topsecret'));
  expect(bytesToHex(seen[0]).includes(needle)).toBe(false);
});
