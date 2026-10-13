// Signed, content-opaque unit both transports carry. Serialization matches the Python reference
// byte-for-byte (verified by the cross-language conformance vectors).
import { concatBytes, pack, unpack, view } from './wire';

export class Envelope {
  constructor(
    public eid: bigint,
    public room: Uint8Array,
    public sender: Uint8Array,
    public prev: bigint[],
    public epoch: bigint,
    public ciphertext: Uint8Array,
    public sig: Uint8Array = new Uint8Array(0),
  ) {}

  body(): Uint8Array {
    const parents = new Uint8Array(2 + 8 * this.prev.length);
    const pv = view(parents);
    pv.setUint16(0, this.prev.length, false);
    this.prev.forEach((p, i) => pv.setBigUint64(2 + 8 * i, p, false));

    const head = new Uint8Array(17);
    const hv = view(head);
    head[0] = 0x01;
    hv.setBigUint64(1, this.eid, false);
    hv.setBigInt64(9, this.epoch, false);

    return concatBytes(head, pack(this.room), pack(this.sender), pack(parents), pack(this.ciphertext));
  }

  toBytes(): Uint8Array {
    return concatBytes(this.body(), pack(this.sig));
  }

  static fromBytes(buf: Uint8Array): Envelope {
    if (buf[0] !== 0x01) throw new Error('unknown envelope version');
    const v = view(buf);
    const eid = v.getBigUint64(1, false);
    const epoch = v.getBigInt64(9, false);

    let off = 17;
    let room: Uint8Array;
    let sender: Uint8Array;
    let parentsRaw: Uint8Array;
    let ciphertext: Uint8Array;
    let sig: Uint8Array;
    [room, off] = unpack(buf, off);
    [sender, off] = unpack(buf, off);
    [parentsRaw, off] = unpack(buf, off);
    [ciphertext, off] = unpack(buf, off);
    [sig, off] = unpack(buf, off);

    const pv = view(parentsRaw);
    const count = pv.getUint16(0, false);
    const prev: bigint[] = [];
    for (let i = 0; i < count; i++) prev.push(pv.getBigUint64(2 + 8 * i, false));

    return new Envelope(eid, room, sender, prev, epoch, ciphertext, sig);
  }
}
