const TZ = "Europe/London";

export const mw = (v) => (v == null ? "-" : `${Math.round(v).toLocaleString("en-GB")} MW`);
export const num = (v) => (v == null ? "-" : Math.round(v).toLocaleString("en-GB"));
export const pct = (v, d = 1) => (v == null ? "-" : `${v.toFixed(d)}%`);
export const pad = (n) => String(n).padStart(2, "0");
export const clock = (c) => `${pad(c.hour)}:${pad(c.minute)}`;

export const dayLabel = (iso) =>
  new Date(`${iso}T12:00:00Z`).toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" });

export const dateTime = (iso) =>
  new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: TZ });

export const slotOf = (iso) =>
  new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: TZ });

export const shortDay = (ms) =>
  new Date(ms).toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: TZ });
