// Bootstrap a Double Ratchet pair for a 1:1 conversation.
//
// In production the root key and the responder's initial ratchet (pre)key come from the
// authenticated handshake (Noise-XX / an X3DH-style prekey exchanged over the BLE handshake). Here,
// where both identities are known in-process (the single-device demo), we derive the root key from
// the static X25519 agreement between the two identities and mint the responder a fresh ratchet
// key — which is exactly the state a completed handshake hands to the ratchet. From that point on
// the real Double Ratchet runs (forward secrecy + post-compromise security), identical to device.
import { x25519 } from '@noble/curves/ed25519';
import { utf8ToBytes } from '@noble/hashes/utils';

import { DoubleRatchet, hkdf, IdentityKeyPair } from '@messenger/crypto';

export interface RatchetPair {
  initiator: DoubleRatchet;
  responder: DoubleRatchet;
}

export function bootstrapRatchets(initiator: IdentityKeyPair, responder: IdentityKeyPair): RatchetPair {
  const rootKey = hkdf(initiator.dh(responder.public.agreementPub), 32, undefined, utf8ToBytes('session-root/v0'));
  const responderRatchetPriv = x25519.utils.randomSecretKey();
  const responderRatchetPub = x25519.getPublicKey(responderRatchetPriv);
  return {
    initiator: DoubleRatchet.initAlice(rootKey, responderRatchetPub),
    responder: DoubleRatchet.initBob(rootKey, responderRatchetPriv),
  };
}
