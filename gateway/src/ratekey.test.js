import assert from "node:assert/strict";
import crypto from "node:crypto";
import { once } from "node:events";
import test from "node:test";

import { clientIp, parseTrustedProxies, rateLimitKey, verifiedSubject } from "./ratekey.js";
import { createApp } from "./server.js";

const { publicKey, privateKey } = crypto.generateKeyPairSync("rsa", { modulusLength: 2048 });
const JWT = { publicKey, algorithm: "RS256", issuer: "https://issuer.test/", audience: "kontur-api" };

function sign(claims, key = privateKey) {
  const enc = (value) => Buffer.from(JSON.stringify(value)).toString("base64url");
  const body = `${enc({ alg: "RS256", typ: "JWT" })}.${enc(claims)}`;
  const signature = crypto.sign("sha256", Buffer.from(body), key).toString("base64url");
  return `${body}.${signature}`;
}

const now = Math.floor(Date.now() / 1000);
const good = { sub: "inspector-1", iss: JWT.issuer, aud: JWT.audience, exp: now + 600, nbf: now - 1 };

function fakeReq(remoteAddress, headers = {}) {
  const lower = Object.fromEntries(Object.entries(headers).map(([k, v]) => [k.toLowerCase(), v]));
  return { socket: { remoteAddress }, headers: lower, header: (name) => lower[name.toLowerCase()] };
}

test("verified JWT subject becomes the key", () => {
  const req = fakeReq("10.0.0.5", { authorization: `Bearer ${sign(good)}` });
  assert.equal(rateLimitKey(req, { jwt: JWT, trustedProxies: new Set() }), "sub:inspector-1");
});

test("unverifiable tokens fall back to the IP key", () => {
  const other = crypto.generateKeyPairSync("rsa", { modulusLength: 2048 }).privateKey;
  for (const token of [
    sign(good, other),
    sign({ ...good, exp: now - 1 }),
    sign({ ...good, aud: "other" }),
    sign({ ...good, iss: "https://evil.test/" }),
    "not-a-jwt",
  ]) {
    assert.equal(verifiedSubject(`Bearer ${token}`, JWT), null);
    const req = fakeReq("10.0.0.5", { authorization: `Bearer ${token}` });
    assert.equal(rateLimitKey(req, { jwt: JWT, trustedProxies: new Set() }), "ip:10.0.0.5");
  }
  assert.equal(verifiedSubject(`Bearer ${sign(good)}`, null), null);
});

test("X-Forwarded-For is honoured from a trusted proxy only", () => {
  const trusted = parseTrustedProxies("10.0.0.2, 10.0.0.3");
  const viaProxy = fakeReq("::ffff:10.0.0.2", { "x-forwarded-for": "203.0.113.7, 10.0.0.3" });
  assert.equal(clientIp(viaProxy, trusted), "203.0.113.7");
  const spoofed = fakeReq("198.51.100.9", { "x-forwarded-for": "203.0.113.7" });
  assert.equal(clientIp(spoofed, trusted), "198.51.100.9");
  const prepended = fakeReq("10.0.0.2", { "x-forwarded-for": "1.1.1.1, 198.51.100.9" });
  assert.equal(clientIp(prepended, trusted), "198.51.100.9");
});

test("spoofed X-Forwarded-For from an untrusted peer cannot dodge the limiter", async () => {
  const app = createApp({ finalizeLimit: 1, coreUrl: "http://127.0.0.1:9", jwt: null, trustedProxies: "10.9.9.9" });
  const server = app.listen(0, "127.0.0.1");
  await once(server, "listening");
  const { port } = server.address();
  const post = (xff) =>
    fetch(`http://127.0.0.1:${port}/api/v1/processes/p-1/finalize`, {
      method: "POST",
      headers: { "content-type": "application/json", "x-forwarded-for": xff },
      body: "{}",
    });
  try {
    const first = await post("203.0.113.1");
    await first.arrayBuffer();
    const second = await post("203.0.113.2");
    await second.arrayBuffer();
    assert.equal(second.status, 429);
  } finally {
    server.close();
  }
});

test("verified subjects get separate buckets behind one address", async () => {
  const app = createApp({ finalizeLimit: 1, coreUrl: "http://127.0.0.1:9", jwt: JWT, trustedProxies: "" });
  const server = app.listen(0, "127.0.0.1");
  await once(server, "listening");
  const { port } = server.address();
  const post = (sub) =>
    fetch(`http://127.0.0.1:${port}/api/v1/processes/p-1/finalize`, {
      method: "POST",
      headers: { "content-type": "application/json", authorization: `Bearer ${sign({ ...good, sub })}` },
      body: "{}",
    });
  try {
    const a = await post("a");
    await a.arrayBuffer();
    const b = await post("b");
    await b.arrayBuffer();
    assert.notEqual(b.status, 429);
    const again = await post("a");
    await again.arrayBuffer();
    assert.equal(again.status, 429);
  } finally {
    server.close();
  }
});
