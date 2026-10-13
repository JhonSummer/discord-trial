// 64-bit time-ordered ids (uses bigint since ids exceed JS's safe integer range).
// Byte-for-byte compatible with the Python Snowflake, including the clock-regression clamp.

export const EPOCH_MS = 1_704_067_200_000n; // 2024-01-01T00:00:00Z

export class Snowflake {
  readonly nodeId: bigint;
  private seq = 0n;
  private last = 0n;

  constructor(nodeId: number | bigint) {
    this.nodeId = BigInt(nodeId) & 0x3ffn;
  }

  next(nowMs?: number | bigint): bigint {
    let now = nowMs === undefined ? BigInt(Date.now()) : BigInt(nowMs);
    if (now <= this.last) {
      now = this.last; // clamp up so ids stay monotonic even if the clock drifts back
      this.seq = (this.seq + 1n) & 0xfffn;
      if (this.seq === 0n) now = this.last + 1n;
    } else {
      this.seq = 0n;
    }
    this.last = now;
    return ((now - EPOCH_MS) << 22n) | (this.nodeId << 12n) | this.seq;
  }

  static timestampMs(eid: bigint): bigint {
    return (eid >> 22n) + EPOCH_MS;
  }
}
