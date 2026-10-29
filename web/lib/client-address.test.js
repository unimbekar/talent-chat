const { test } = require("node:test");
const assert = require("node:assert/strict");
const { visitorAddress } = require("./client-address");

test("a direct connection keeps the peer and ignores a forwarded address", () => {
  assert.equal(visitorAddress("192.168.1.185", "8.8.8.8"), "192.168.1.185");
  assert.equal(visitorAddress("::ffff:192.168.1.185", "1.1.1.1"), "192.168.1.185");
});

test("loopback uses the address the local proxy saw", () => {
  assert.equal(visitorAddress("127.0.0.1", "8.8.8.8"), "8.8.8.8");
  assert.equal(visitorAddress("::1", "203.0.113.10"), "203.0.113.10");
  assert.equal(visitorAddress("127.0.0.1", "1.2.3.4, 8.8.8.8"), "8.8.8.8");
  assert.equal(visitorAddress("::ffff:127.0.0.1", "  8.8.4.4  "), "8.8.4.4");
});

test("loopback without a real forwarded address stays local", () => {
  assert.equal(visitorAddress("127.0.0.1", ""), "127.0.0.1");
  assert.equal(visitorAddress("127.0.0.1", "127.0.0.1"), "127.0.0.1");
  assert.equal(visitorAddress("127.0.0.1", "not-an-ip"), "127.0.0.1");
});
