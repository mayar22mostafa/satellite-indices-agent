// Unique id. crypto.randomUUID only exists on HTTPS or localhost,
// so a fallback keeps the app working when tested over http on a phone.
export const createId = () =>
  crypto.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`;