"""Runnable Phase 1 deliverable: two devices become friends and exchange E2EE messages
through an untrusted relay that only ever sees ciphertext.

This is the executable form of what ``tests/test_relay.py`` asserts, and the realization of
the roadmap's Phase 1 deliverable (``../docs/06-roadmap.md``). Like ``sim/run_sweep.py`` it is
a plain entry point:

    cd crypto && python3 demo.py

It prints a transcript of a Noise handshake + safety-number check, a 1:1 Double-Ratchet
exchange, and an MLS group exchange — each routed through the relay — and shows that every
blob the relay handled is opaque ciphertext. No keys or secrets are printed.
"""

from __future__ import annotations

from cryptocore import (
    DoubleRatchet,
    Group,
    GroupError,
    Header,
    IdentityKeyPair,
    UntrustedRelay,
    hkdf,
    run_handshake,
    safety_number,
)
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


def _preview(blob: bytes, n: int = 24) -> str:
    return blob[:n].hex() + ("…" if len(blob) > n else "")


def _ratchet_root(result) -> bytes:
    lo, hi = sorted([result.send_key, result.recv_key])
    return hkdf(lo + hi, 32, info=b"phase1/ratchet-root")


def run_demo(verbose: bool = True) -> dict:
    def say(*args):
        if verbose:
            print(*args)

    result: dict = {"relay_saw_plaintext": False}
    relay = UntrustedRelay()
    relayed: list[tuple[bytes, bytes]] = []  # (plaintext, ciphertext-blob) the relay carried

    def send(recipients, plaintext, blob, sender):
        relay.fanout(recipients, blob, sender=sender)
        relayed.append((plaintext, blob))

    # --- 1. Handshake + safety number = becoming friends -----------------------------------
    say("== 1. Noise XX handshake + safety-number verification ==")
    alice_id, bob_id = IdentityKeyPair.generate(), IdentityKeyPair.generate()
    alice_hs, bob_hs = run_handshake(alice_id, bob_id)
    alice_sn = safety_number(alice_id.public, alice_hs.peer)
    bob_sn = safety_number(bob_id.public, bob_hs.peer)
    result["safety_number_match"] = alice_sn == bob_sn
    say(f"   Alice authenticated peer fp {alice_hs.peer.fingerprint_hex[:16]}…")
    say(f"   Bob   authenticated peer fp {bob_hs.peer.fingerprint_hex[:16]}…")
    say(f"   Safety number (both screens): {alice_sn}")
    say(f"   -> match, no man-in-the-middle: {result['safety_number_match']}\n")

    # --- 2. 1:1 messaging through the relay ------------------------------------------------
    say("== 2. 1:1 Double-Ratchet messages through the untrusted relay ==")
    root = _ratchet_root(alice_hs)
    bob_prekey = X25519PrivateKey.generate()
    bob_prekey_pub = bob_prekey.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    alice_dr = DoubleRatchet.init_alice(root, bob_prekey_pub)
    bob_dr = DoubleRatchet.init_bob(root, bob_prekey)
    a_handle, b_handle = alice_id.public.fingerprint_hex, bob_id.public.fingerprint_hex

    m1 = b"hey Bob -- meet at the usual place, 9pm"
    header, body = alice_dr.encrypt(m1)
    blob = header.serialize() + body
    send([b_handle], m1, blob, sender=a_handle)
    say(f"   Alice -> relay : plaintext  {m1!r}")
    say(f"   relay stores   : ciphertext {_preview(relay.peek(b_handle)[0].payload)}")
    (to_bob,) = relay.deliver(b_handle)
    got1 = bob_dr.decrypt(Header.deserialize(to_bob.payload[:40]), to_bob.payload[40:])
    say(f"   relay -> Bob   : decrypted  {got1!r}")
    result["alice_to_bob_ok"] = got1 == m1

    m2 = b"sounds good, see you there"
    h2, b2 = bob_dr.encrypt(m2)
    blob2 = h2.serialize() + b2
    send([a_handle], m2, blob2, sender=b_handle)
    (to_alice,) = relay.deliver(a_handle)
    got2 = alice_dr.decrypt(Header.deserialize(to_alice.payload[:40]), to_alice.payload[40:])
    say(f"   Bob -> relay -> Alice : {got2!r}")
    result["bob_to_alice_ok"] = got2 == m2
    say("")

    # --- 3. MLS group messaging through the relay -----------------------------------------
    say("== 3. MLS group message fanned out through the relay ==")
    group = Group.create(3)  # slot 0 Alice, 1 Bob, 2 Carol
    names = {0: "alice", 1: "bob", 2: "carol"}
    g1 = b"group: dinner at 8 tonight?"
    gblob = group.member(0).encrypt_message(g1)
    send([names[1], names[2]], g1, gblob, sender=names[0])
    say(f"   Alice -> relay : plaintext  {g1!r}")
    say(f"   relay stores   : ciphertext {_preview(relay.peek('bob')[0].payload)} (x2 fanout)")
    bob_got = group.member(1).decrypt_message(relay.deliver("bob")[0].payload)
    carol_got = group.member(2).decrypt_message(relay.deliver("carol")[0].payload)
    say(f"   relay -> Bob   : {bob_got!r}")
    say(f"   relay -> Carol : {carol_got!r}")
    result["group_delivered_ok"] = bob_got == g1 and carol_got == g1
    say("")

    # --- 4. Remove a member; it can no longer read relayed traffic -------------------------
    say("== 4. Evict Carol, re-key, and send again ==")
    carol, _ = group.remove(2, remover=0)
    g2 = b"group: actually, new venue -- the rooftop"
    gblob2 = group.member(0).encrypt_message(g2)
    send([names[1], names[2]], g2, gblob2, sender=names[0])
    bob_got2 = group.member(1).decrypt_message(relay.deliver("bob")[0].payload)
    say(f"   relay -> Bob   : {bob_got2!r}")
    carol_blob = relay.deliver("carol")[0].payload  # relay still forwards her the bytes...
    try:
        carol.decrypt_message(carol_blob)            # ...but she cannot read them.
        result["evicted_member_blocked"] = False
    except GroupError:
        result["evicted_member_blocked"] = True
    say(f"   relay -> Carol : forwarded, but Carol can no longer decrypt: "
        f"{result['evicted_member_blocked']}")
    say("")

    # --- Invariant: the relay never held any plaintext ------------------------------------
    for plaintext, blob in relayed:
        if plaintext in blob:
            result["relay_saw_plaintext"] = True
    result["relay_posted"] = relay.posted
    result["relay_delivered"] = relay.delivered
    say("== Summary ==")
    say(f"   relay handled {relay.posted} blobs, delivered {relay.delivered}")
    say(f"   relay ever saw plaintext: {result['relay_saw_plaintext']}")
    return result


def main() -> None:
    r = run_demo(verbose=True)
    ok = (
        r["safety_number_match"]
        and r["alice_to_bob_ok"]
        and r["bob_to_alice_ok"]
        and r["group_delivered_ok"]
        and r["evicted_member_blocked"]
        and not r["relay_saw_plaintext"]
    )
    print("\nDELIVERABLE OK" if ok else "\nDELIVERABLE FAILED")


if __name__ == "__main__":
    main()
