export type Brand = {
  company_name: string;
  careers_url: string;
  tagline: string;
  accent: string;
  logo_url: string;
  hero_url: string;
  footer: string;
  examples: string[];
};

export const DEFAULT_BRAND: Brand = {
  company_name: "Janus Soft Inc.",
  careers_url: "https://www.janus-soft.com/career",
  tagline: "Find the role that fits you",
  accent: "#857251",
  logo_url: "/brand/logo.svg",
  hero_url: "/brand/hero.webp",
  footer: "",
  examples: ["Java, Python, and AWS jobs", "Jobs in Chantilly", "Do any roles need a clearance?"],
};
