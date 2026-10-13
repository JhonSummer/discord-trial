// Length-prefix framing shared with the Python reference: big-endian uint32 length + bytes.
import { concatBytes } from '@noble/hashes/utils';

export { concatBytes };

export function view(b: Uint8Array): DataView {
  return new DataView(b.buffer, b.byteOffset, b.byteLength);
}

export function pack(b: Uint8Array): Uint8Array {
  const out = new Uint8Array(4 + b.length);
  view(out).setUint32(0, b.length, false);
  out.set(b, 4);
  return out;
}

export function unpack(buf: Uint8Array, off: number): [Uint8Array, number] {
  const n = view(buf).getUint32(off, false);
  const start = off + 4;
  return [buf.slice(start, start + n), start + n];
}
