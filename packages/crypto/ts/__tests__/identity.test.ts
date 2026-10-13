import { IdentityKeyPair, PublicIdentity, safetyNumber } from '../src';
import { utf8ToBytes } from '@noble/hashes/utils';

const seed = (start: number) => Uint8Array.from({ length: 32 }, (_, i) => start + i);

function pair(signStart: number, agreeStart: number): IdentityKeyPair {
  return IdentityKeyPair.fromSeeds(seed(signStart), seed(agreeStart));
}

test('public keys are deterministic for fixed seeds', () => {
  const a = pair(0, 32).public;
  const b = pair(0, 32).public;
  expect([...a.signingPub]).toEqual([...b.signingPub]);
  expect([...a.agreementPub]).toEqual([...b.agreementPub]);
  expect([...a.fingerprint]).toEqual([...b.fingerprint]);
});

test('signatures verify and detect tampering', () => {
  const alice = pair(0, 32);
  const msg = utf8ToBytes('authenticate me');
  const sig = alice.sign(msg);
  expect(alice.public.verify(sig, msg)).toBe(true);
  expect(alice.public.verify(sig, utf8ToBytes('different'))).toBe(false);
  expect(pair(64, 96).public.verify(sig, msg)).toBe(false);
});

test('diffie-hellman agrees in both directions', () => {
  const alice = pair(0, 32);
  const bob = pair(64, 96);
  expect([...alice.dh(bob.public.agreementPub)]).toEqual([...bob.dh(alice.public.agreementPub)]);
});

test('public identity serialization roundtrips', () => {
  const pub = pair(0, 32).public;
  const back = PublicIdentity.deserialize(pub.serialize());
  expect([...back.signingPub]).toEqual([...pub.signingPub]);
  expect([...back.agreementPub]).toEqual([...pub.agreementPub]);
});

test('safety number is symmetric and grouped', () => {
  const alice = pair(0, 32).public;
  const bob = pair(64, 96).public;
  const ab = safetyNumber(alice, bob);
  expect(safetyNumber(bob, alice)).toBe(ab);
  expect(ab.replace(/ /g, '')).toHaveLength(60);
  expect(ab.split(' ')).toHaveLength(12);
});
