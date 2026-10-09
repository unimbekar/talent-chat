// Renders the installable-app icons from public/brand/logo.svg.
// Run after changing the logo: node scripts/make-icons.mjs
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import sharp from "sharp";

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
const logo = path.join(root, "public/brand/logo.svg");
const out = path.join(root, "public/icons");
const background = "#1d1c1a";

await mkdir(out, { recursive: true });

async function plain(size, name) {
  await sharp(logo, { density: 1024 }).resize(size, size).png().toFile(path.join(out, name));
}

// Android crops maskable icons to a circle or squircle; keep the mark inside the 80% safe zone.
async function maskable(size, name) {
  const inner = Math.round(size * 0.72);
  const mark = await sharp(logo, { density: 1024 }).resize(inner, inner).png().toBuffer();
  await sharp({ create: { width: size, height: size, channels: 4, background } })
    .composite([{ input: mark, gravity: "center" }])
    .png()
    .toFile(path.join(out, name));
}

// iOS draws its own rounded corners and ignores transparency, so fill the square.
async function apple(size, name) {
  const inner = Math.round(size * 0.86);
  const mark = await sharp(logo, { density: 1024 }).resize(inner, inner).png().toBuffer();
  await sharp({ create: { width: size, height: size, channels: 4, background } })
    .composite([{ input: mark, gravity: "center" }])
    .png()
    .toFile(path.join(out, name));
}

await plain(192, "icon-192.png");
await plain(512, "icon-512.png");
await maskable(192, "maskable-192.png");
await maskable(512, "maskable-512.png");
await apple(180, "apple-touch-icon.png");
await plain(96, "shortcut-96.png");
console.log(`Icons written to ${out}`);
