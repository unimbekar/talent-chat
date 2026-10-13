const { createServer } = require("http");
const { parse } = require("url");
const next = require("next");

const port = Number(process.env.PORT || 3000);
const app = next({ dev: false, hostname: "0.0.0.0", port });
const handle = app.getRequestHandler();

function plain(ip) {
  const text = String(ip || "").trim();
  return text.startsWith("::ffff:") ? text.slice(7) : text;
}

app.prepare().then(() => {
  createServer((req, res) => {
    // The TCP peer, never a header the browser sent.
    req.headers["x-visitor-address"] = plain(req.socket.remoteAddress);
    handle(req, res, parse(req.url || "/", true));
  }).listen(port, "0.0.0.0");
});
