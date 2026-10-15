// Rate-limit key: verified JWT subject when the token checks out, otherwise the client IP.
// X-Forwarded-For is honoured only when the direct peer is a configured trusted proxy.

import crypto from "node:crypto";

const HASHES = { RS256: "sha256", ES256: "sha256", RS384: "sha384", ES384: "sha384" };

function normalizeIp(address) {
  if (typeof address !== "string" || !address) return "unknown";
  return address.startsWith("::ffff:") ? address.slice(7) : address;
}

export function parseTrustedProxies(value) {
  return new Set(
    String(value ?? "")
      .split(",")
      .map((item) => normalizeIp(item.trim()))
      .filter((item) => item && item !== "unknown"),
  );
}

/** Client IP: the right-most X-Forwarded-For hop that is not a trusted proxy. */
export function clientIp(req, trustedProxies) {
  const peer = normalizeIp(req.socket?.remoteAddress);
  if (!trustedProxies.has(peer)) return peer;
  const header = req.headers["x-forwarded-for"];
  if (typeof header !== "string" || !header.trim()) return peer;
  const hops = header.split(",").map((hop) => normalizeIp(hop.trim()));
  for (let i = hops.length - 1; i >= 0; i -= 1) {
    if (!trustedProxies.has(hops[i])) return hops[i];
  }
  return hops[0] ?? peer;
}

function decodeSegment(segment) {
  return JSON.parse(Buffer.from(segment, "base64url").toString("utf8"));
}

/** Subject of a JWT whose signature, algorithm, iss, aud, exp and nbf all check out; else null. */
export function verifiedSubject(authorization, config, nowSeconds = Date.now() / 1000) {
  if (!config?.publicKey || typeof authorization !== "string") return null;
  if (!authorization.toLowerCase().startsWith("bearer ")) return null;
  const parts = authorization.slice(7).trim().split(".");
  if (parts.length !== 3) return null;
  try {
    const header = decodeSegment(parts[0]);
    const algorithm = config.algorithm ?? "RS256";
    const hash = HASHES[algorithm];
    if (!hash || header.alg !== algorithm) return null;
    const ok = crypto.verify(
      hash,
      Buffer.from(`${parts[0]}.${parts[1]}`),
      algorithm.startsWith("ES")
        ? { key: config.publicKey, dsaEncoding: "ieee-p1363" }
        : config.publicKey,
      Buffer.from(parts[2], "base64url"),
    );
    if (!ok) return null;
    const claims = decodeSegment(parts[1]);
    if (typeof claims.exp !== "number" || claims.exp <= nowSeconds) return null;
    if (typeof claims.nbf === "number" && claims.nbf > nowSeconds) return null;
    if (config.issuer && claims.iss !== config.issuer) return null;
    if (config.audience) {
      const aud = Array.isArray(claims.aud) ? claims.aud : [claims.aud];
      if (!aud.includes(config.audience)) return null;
    }
    return typeof claims.sub === "string" && claims.sub.trim() ? claims.sub.trim() : null;
  } catch {
    return null;
  }
}

export function rateLimitKey(req, { jwt, trustedProxies }) {
  const sub = verifiedSubject(req.header("authorization") ?? "", jwt);
  return sub ? `sub:${sub}` : `ip:${clientIp(req, trustedProxies)}`;
}

export function jwtConfigFromEnv(env = process.env) {
  const publicKey = (env.KONTUR_JWT_PUBLIC_KEY ?? "").replace(/\\n/g, "\n").trim();
  if (!publicKey.includes("BEGIN PUBLIC KEY")) return null;
  try {
    return {
      publicKey: crypto.createPublicKey(publicKey),
      algorithm: env.KONTUR_JWT_ALGORITHM || "RS256",
      issuer: env.KONTUR_JWT_ISSUER || "",
      audience: env.KONTUR_JWT_AUDIENCE || "",
    };
  } catch {
    return null;
  }
}
