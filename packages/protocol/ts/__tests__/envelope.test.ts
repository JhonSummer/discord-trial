import { Envelope } from '../src';

const enc = (s: string) => new TextEncoder().encode(s);

test('envelope roundtrips', () => {
  const env = new Envelope(123n, enc('room'), new Uint8Array(32).fill(7), [1n, 2n], 4n, enc('ct'), enc('sig'));
  const back = Envelope.fromBytes(env.toBytes());
  expect(back.eid).toBe(123n);
  expect(back.epoch).toBe(4n);
  expect(back.prev).toEqual([1n, 2n]);
  expect([...back.ciphertext]).toEqual([...enc('ct')]);
  expect([...back.toBytes()]).toEqual([...env.toBytes()]);
});

test('body is deterministic', () => {
  const mk = () => new Envelope(1n, enc('r'), new Uint8Array(32), [2n, 3n], 1n, enc('x'));
  expect([...mk().body()]).toEqual([...mk().body()]);
});
