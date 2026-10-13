// In-process transport: every endpoint broadcasts each frame to all other attached endpoints.
// Stands in for the real relay / BLE mesh so the app core runs with no network and no radios,
// which is what makes the view-model testable headless (see __tests__/conversation.test.ts).
import { Transport } from './types';

export class LoopbackBus {
  private readonly deliverers = new Set<(frame: Uint8Array) => void>();

  endpoint(): Transport {
    const handlers = new Set<(frame: Uint8Array) => void>();
    const deliver = (frame: Uint8Array) => handlers.forEach((h) => h(frame));
    this.deliverers.add(deliver);
    return {
      send: (frameBytes) => {
        for (const other of this.deliverers) if (other !== deliver) other(frameBytes);
      },
      subscribe: (handler) => {
        handlers.add(handler);
        return () => handlers.delete(handler);
      },
    };
  }
}
