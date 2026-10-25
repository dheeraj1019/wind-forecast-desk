const API_BASE_URL = "https://wind-forecast-desk-7y50.onrender.com";

async function get(path, params = {}) {
  const qs = new URLSearchParams(params).toString();

  const res = await fetch(
    `${API_BASE_URL}/api/${path}${qs ? `?${qs}` : ""}`
  );

  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`;

    try {
      const body = await res.json();
      if (body.detail) {
        msg =
          typeof body.detail === "string"
            ? body.detail
            : JSON.stringify(body.detail);
      }
    } catch {
      // Keep the default error message.
    }

    throw new Error(msg);
  }

  return res.json();
}

export const api = {
  meta: () => get("meta"),
  decision: (p) => get("decision", p),
  evaluation: (p) => get("evaluation", p),
};