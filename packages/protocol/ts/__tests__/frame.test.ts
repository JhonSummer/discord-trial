import { DEFAULT_TTL, Frame, MSG_ID_LEN } from '../src';

test('frame roundtrips', () => {
  const f = new Frame(5, Uint8Array.of(0, 1, 2, 255));
  const g = Frame.fromBytes(f.toBytes());
  expect(g.ttl).toBe(5);
  expect([...g.payload]).toEqual([0, 1, 2, 255]);
});

test('msg id is content-addressed and ttl-independent', () => {
  const a = new Frame(5, Uint8Array.of(1, 2, 3));
  const b = new Frame(1, Uint8Array.of(1, 2, 3));
  const c = new Frame(5, Uint8Array.of(9));
  expect([...a.msgId]).toEqual([...b.msgId]);
  expect([...a.msgId]).not.toEqual([...c.msgId]);
  expect(a.msgId.length).toBe(MSG_ID_LEN);
});

test('hop decrements until dead', () => {
  const f = new Frame(2, new Uint8Array());
  expect(f.alive).toBe(true);
  expect(f.hop().ttl).toBe(1);
  expect(f.hop().hop().alive).toBe(false);
  expect(DEFAULT_TTL).toBeGreaterThan(0);
});
