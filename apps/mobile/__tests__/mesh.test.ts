import { bytesToHex, utf8ToBytes } from '@noble/hashes/utils';

import { IdentityKeyPair } from '@messenger/crypto';
import { MeshRouter } from '@messenger/transport';

import { Conversation } from '../src/core/conversation';
import { bootstrapRatchets } from '../src/core/session';
import { MeshRouterTransport } from '../src/transport/meshRouterTransport';

const room = utf8ToBytes('general');
const seed = (start: number) => Uint8Array.from({ length: 32 }, (_, i) => start + i);
const pair = (signStart: number, agreeStart: number) =>
  IdentityKeyPair.fromSeeds(seed(signStart), seed(agreeStart));

function wire(a: MeshRouter, b: MeshRouter): void {
  a.connect(b.nodeId, (data) => b.onFrame(data, a.nodeId));
  b.connect(a.nodeId, (data) => a.onFrame(data, b.nodeId));
}

test('E2EE conversation over a multi-hop mesh; the relay carries only ciphertext', () => {
  const alice = pair(0, 32);
  const bob = pair(64, 96);

  // Line A—B—C: Alice is on A, Bob is on C, B is a pure relay (no conversation).
  const ra = new MeshRouter('A');
  const rb = new MeshRouter('B');
  const rc = new MeshRouter('C');
  wire(ra, rb);
  wire(rb, rc);

  const { initiator, responder } = bootstrapRatchets(alice, bob);
  const aliceConv = new Conversation(alice, bob.public, room, new MeshRouterTransport(ra), initiator, 1);
  const bobConv = new Conversation(bob, alice.public, room, new MeshRouterTransport(rc), responder, 2);

  aliceConv.send('through the relay');
  expect(bobConv.messages.map((m) => m.text)).toEqual(['through the relay']);

  bobConv.send('reply via relay'); // Bob can reply once his ratchet sending chain exists
  expect(aliceConv.messages.map((m) => m.text)).toEqual(['through the relay', 'reply via relay']);

  // B relayed envelopes in both directions but cannot read them.
  expect(rb.delivered.length).toBeGreaterThanOrEqual(2);
  const needle = bytesToHex(utf8ToBytes('through the relay'));
  for (const payload of rb.delivered) {
    expect(bytesToHex(payload).includes(needle)).toBe(false);
  }
});
