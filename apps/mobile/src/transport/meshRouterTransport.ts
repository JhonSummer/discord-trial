// A Transport backed by the ported flood MeshRouter (@messenger/transport). This is the same
// routing core the Bumble emulation suite verifies; here it carries the app's envelopes over a
// multi-hop mesh. `send` originates an envelope into the mesh; delivered envelopes are fanned out
// to subscribers. On device the router's links are GATT connections; in tests they're direct calls.
import { MeshRouter } from '@messenger/transport';

import { Transport } from './types';

export class MeshRouterTransport implements Transport {
  private readonly handlers = new Set<(payload: Uint8Array) => void>();

  constructor(private readonly router: MeshRouter) {
    this.router.onDeliver = (payload) => this.handlers.forEach((h) => h(payload));
  }

  send(payload: Uint8Array): void {
    this.router.originate(payload);
  }

  subscribe(handler: (payload: Uint8Array) => void): () => void {
    this.handlers.add(handler);
    return () => this.handlers.delete(handler);
  }
}
