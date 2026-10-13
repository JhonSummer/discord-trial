import { EPOCH_MS, Snowflake } from '../src';

test('ids are time-ordered and encode the node id', () => {
  const sf = new Snowflake(42);
  const a = sf.next(EPOCH_MS + 1000n);
  const b = sf.next(EPOCH_MS + 2000n);
  expect(b > a).toBe(true);
  expect((a >> 12n) & 0x3ffn).toBe(42n);
  expect(Snowflake.timestampMs(a)).toBe(EPOCH_MS + 1000n);
});

test('ids stay monotonic when the clock goes backwards', () => {
  const sf = new Snowflake(1);
  const first = sf.next(EPOCH_MS + 100n);
  const later = [sf.next(EPOCH_MS + 50n), sf.next(EPOCH_MS + 50n)];
  expect(later[0] > first).toBe(true);
  expect(later[1] > later[0]).toBe(true);
});
