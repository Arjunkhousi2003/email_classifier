const TOKEN_KEY = "email_classifier_token";

export type Category = {
  slug: string;
  name: string;
  description: string;
  count: number;
};

export type MailItem = {
  id: string;
  provider: string;
  sender: string | null;
  subject: string | null;
  snippet: string | null;
  body_text: string | null;
  received_at: string | null;
  category: string;
  confidence: number | null;
  classification_source: string | null;
};

export type SessionUser = {
  id: string;
  email: string;
  name: string | null;
  gmail_connected: boolean;
  imap_accounts: { host: string; username: string; port: number }[];
};

export function readToken(): string | null {
  return sessionStorage.getItem(TOKEN_KEY);
}

export function saveToken(value: string): void {
  sessionStorage.setItem(TOKEN_KEY, value);
}

export function clearToken(): void {
  sessionStorage.removeItem(TOKEN_KEY);
}

function messageFrom(body: { detail?: unknown }): string {
  if (typeof body.detail === "string") return body.detail;
  if (Array.isArray(body.detail)) {
    return body.detail
      .map((item) => (item && typeof item === "object" && "msg" in item ? String(item.msg) : "Invalid request"))
      .join(", ");
  }
  return "Request failed";
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body) headers.set("Content-Type", "application/json");
  const current = readToken();
  if (current) headers.set("Authorization", `Bearer ${current}`);
  const response = await fetch(path, { ...init, headers });
  if (response.status === 401) {
    clearToken();
    throw new Error("Sign in again");
  }
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { detail?: unknown };
    throw new Error(messageFrom(body));
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
