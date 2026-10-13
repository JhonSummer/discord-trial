// TypeScript side of the cross-language conformance suite. Asserts the app's TS implementation
// reproduces every value in tests/vectors/conformance.json byte-for-byte. The Python suite
// (tests/test_conformance.py) asserts the same file, so green on both sides proves one shared
// wire format and one set of crypto primitives. Ed25519 is deterministic (RFC 8032), so even the
// signature matches exactly across languages. Regenerate: python3 tests/vectors/gen_vectors.py
import { readFileSync } from 'fs';
import { join } from 'path';

import { bytesToHex, hexToBytes } from '@noble/hashes/utils';

import { Envelope, Frame, Snowflake } from '@messenger/protocol';
import {
  DoubleRatchet,
  Header,
  IdentityKeyPair,
  aeadDecrypt,
  aeadEncrypt,
  hkdf,
  kdfCk,
  kdfRk,
  safetyNumber,
  sha256,
} from '@messenger/crypto';

const V = JSON.parse(readFileSync(join(__dirname, 'vectors', 'conformance.json'), 'utf8'));
const hex = (s: string) => hexToBytes(s);

test('sha256 matches the Python reference', () => {
  expect(bytesToHex(sha256(hex(V.sha256.input_hex)))).toBe(V.sha256.output_hex);
});

test('hkdf matches the Python reference', () => {
  const { ikm_hex, length, salt_hex, info_hex, out_hex } = V.hkdf;
  expect(bytesToHex(hkdf(hex(ikm_hex), length, hex(salt_hex), hex(info_hex)))).toBe(out_hex);
});

test('chacha20-poly1305 matches the Python reference', () => {
  const { key_hex, nonce_hex, ad_hex, plaintext_hex, ciphertext_hex } = V.aead;
  const { ciphertext } = aeadEncrypt(hex(key_hex), hex(plaintext_hex), hex(ad_hex), hex(nonce_hex));
  expect(bytesToHex(ciphertext)).toBe(ciphertext_hex);
  expect(bytesToHex(aeadDecrypt(hex(key_hex), hex(nonce_hex), hex(ciphertext_hex), hex(ad_hex)))).toBe(plaintext_hex);
});

test('identity keys, fingerprint and safety number match', () => {
  const v = V.identity;
  const alice = IdentityKeyPair.fromSeeds(hex(v.alice_sign_seed_hex), hex(v.alice_agree_scalar_hex));
  const bob = IdentityKeyPair.fromSeeds(hex(v.bob_sign_seed_hex), hex(v.bob_agree_scalar_hex));
  expect(bytesToHex(alice.public.signingPub)).toBe(v.alice_signing_pub_hex);
  expect(bytesToHex(alice.public.agreementPub)).toBe(v.alice_agreement_pub_hex);
  expect(bytesToHex(alice.public.fingerprint)).toBe(v.alice_fingerprint_hex);
  expect(safetyNumber(alice.public, bob.public)).toBe(v.safety_number);
});

test('envelope body, deterministic signature and bytes match', () => {
  const v = V.envelope;
  const id = V.identity;
  const alice = IdentityKeyPair.fromSeeds(hex(id.alice_sign_seed_hex), hex(id.alice_agree_scalar_hex));
  const env = new Envelope(
    BigInt(v.eid),
    hex(v.room_hex),
    hex(v.sender_hex),
    v.prev.map((p: string) => BigInt(p)),
    BigInt(v.epoch),
    hex(v.ciphertext_hex),
  );
  env.sig = alice.sign(env.body());
  expect(bytesToHex(env.body())).toBe(v.body_hex);
  expect(bytesToHex(env.sig)).toBe(v.sig_hex);
  expect(bytesToHex(env.toBytes())).toBe(v.bytes_hex);

  const back = Envelope.fromBytes(hex(v.bytes_hex));
  expect(alice.public.verify(back.sig, back.body())).toBe(true);
  expect(bytesToHex(back.toBytes())).toBe(v.bytes_hex);
});

test('frame msg id and bytes match', () => {
  const v = V.frame;
  const frame = new Frame(v.ttl, hex(v.payload_hex));
  expect(bytesToHex(frame.msgId)).toBe(v.msg_id_hex);
  expect(bytesToHex(frame.toBytes())).toBe(v.bytes_hex);
  expect(bytesToHex(Frame.fromBytes(hex(v.bytes_hex)).payload)).toBe(v.payload_hex);
});

test('snowflake ids match, including the clock-regression clamp', () => {
  const v = V.snowflake;
  const sf = new Snowflake(v.node_id);
  for (const call of v.calls) {
    expect(sf.next(call.now_ms).toString()).toBe(call.id);
  }
});

test('double ratchet KDFs match the Python reference', () => {
  const rk = V.ratchet.kdf_rk;
  const [outRk, outCk] = kdfRk(hex(rk.rk_hex), hex(rk.dh_hex));
  expect(bytesToHex(outRk)).toBe(rk.out_rk_hex);
  expect(bytesToHex(outCk)).toBe(rk.out_ck_hex);
  const ck = V.ratchet.kdf_ck;
  const [nextCk, mk] = kdfCk(hex(ck.ck_hex));
  expect(bytesToHex(nextCk)).toBe(ck.out_ck_hex);
  expect(bytesToHex(mk)).toBe(ck.out_mk_hex);
});

test('the TS ratchet decrypts a session encrypted by the Python ratchet', () => {
  const s = V.ratchet.session;
  const bob = DoubleRatchet.initBob(hex(s.root_key_hex), hex(s.bob_ratchet_priv_hex));
  const ad = hex(s.ad_hex);
  for (const m of s.messages) {
    const header = new Header(hex(m.dh_hex), m.pn, m.n);
    expect(bytesToHex(bob.decrypt(header, hex(m.body_hex), ad))).toBe(m.plaintext_hex);
  }
});
