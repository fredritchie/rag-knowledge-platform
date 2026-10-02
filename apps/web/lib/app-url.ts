// OAuth routes must read this at request time. NEXT_PUBLIC_* values are frozen
// during next build and cannot follow an image promoted between environments.
export function appUrl(): URL {
  const value = process.env.APP_URL;
  if (!value) throw new Error("APP_URL is required");
  const url = new URL(value);
  if (!["http:", "https:"].includes(url.protocol) || url.username || url.password ||
      url.pathname !== "/" || url.search || url.hash) {
    throw new Error("APP_URL must be an HTTP(S) origin without credentials, path, query or fragment");
  }
  return url;
}
