const { isIP } = require("net");

function plain(ip) {
  let text = String(ip || "").trim();
  if (text.startsWith("::ffff:")) text = text.slice(7);
  if (text.startsWith("[") && text.endsWith("]")) text = text.slice(1, -1);
  const zone = text.indexOf("%");
  if (zone !== -1) text = text.slice(0, zone);
  return text;
}

function isLoopback(ip) {
  const text = plain(ip);
  if (!isIP(text)) return false;
  return text === "::1" || text.startsWith("127.");
}

function headerText(value) {
  if (Array.isArray(value)) return value.join(",");
  return String(value || "");
}

/** Tailscale Funnel replaces this with the one address it saw. A chain keeps the last hop. */
function forwardedClient(value) {
  const hops = headerText(value)
    .split(",")
    .map((part) => plain(part))
    .filter((part) => isIP(part) && !isLoopback(part));
  return hops.length ? hops[hops.length - 1] : "";
}

/**
 * Address to record for a careers visit.
 * A direct connection uses the TCP peer, so a browser cannot invent its address.
 * Funnel on this machine connects from loopback and supplies the visitor there.
 */
function visitorAddress(peer, forwardedFor) {
  const seen = plain(peer);
  if (isLoopback(seen)) {
    const forwarded = forwardedClient(forwardedFor);
    if (forwarded) return forwarded;
  }
  return isIP(seen) ? seen : "unknown";
}

module.exports = { visitorAddress, isLoopback, plain };
