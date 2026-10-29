const { createServer } = require("http");
const { parse } = require("url");
const next = require("next");
const { visitorAddress } = require("./lib/client-address");

const port = Number(process.env.PORT || 3000);
const app = next({ dev: false, hostname: "0.0.0.0", port });
const handle = app.getRequestHandler();

app.prepare().then(() => {
  createServer((req, res) => {
    // Direct visitors keep the TCP peer. Funnel connects from loopback and
    // puts the real address in X-Forwarded-For; a browser on any other path cannot.
    req.headers["x-visitor-address"] = visitorAddress(req.socket.remoteAddress, req.headers["x-forwarded-for"]);
    handle(req, res, parse(req.url || "/", true));
  }).listen(port, "0.0.0.0");
});
