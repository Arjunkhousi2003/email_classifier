import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  Category,
  FetchResult,
  MailItem,
  SessionUser,
  api,
  clearToken,
  readToken,
  saveToken,
} from "./api";

const SAMPLES = [
  {
    sender: "billing@northwind.test",
    subject: "Invoice 1042 is ready",
    body: "Your invoice for March is attached. Payment is due in 14 days.",
  },
  {
    sender: "prize@lucky.test",
    subject: "You have won the lottery",
    body: "Claim your lottery winnings with a wire transfer today.",
  },
  {
    sender: "deals@shop.test",
    subject: "30% off this weekend",
    body: "Limited time sale. Use the link below to unsubscribe.",
  },
  {
    sender: "alex@studio.test",
    subject: "Lunch on Thursday?",
    body: "Are you free after the design review?",
  },
];

const CATEGORY_ORDER = ["payment", "spam", "promotions", "general"];

function formatWhen(value: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

export function App() {
  const [token, setToken] = useState<string | null>(readToken());
  const [user, setUser] = useState<SessionUser | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [emails, setEmails] = useState<MailItem[]>([]);
  const [active, setActive] = useState("all");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<MailItem | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [mailbox, setMailbox] = useState({ email: "", password: "", host: "" });
  const [emailInput, setEmailInput] = useState("you@example.com");
  const [imap, setImap] = useState({ host: "", username: "", password: "", port: "993" });
  const pendingFetch = useRef(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const incoming = params.get("token");
    if (incoming) {
      saveToken(incoming);
      setToken(incoming);
      window.history.replaceState({}, "", window.location.pathname);
    }
  }, []);

  useEffect(() => {
    if (!token) {
      setUser(null);
      return;
    }
    let cancelled = false;
    api<SessionUser>("/auth")
      .then((next) => {
        if (!cancelled) setUser(next);
      })
      .catch((err: Error) => {
        if (!cancelled) {
          setToken(null);
          setError(err.message);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  async function refreshInbox(nextCategory = active, nextQuery = query) {
    const params = new URLSearchParams();
    if (nextCategory !== "all") params.set("category", nextCategory);
    if (nextQuery.trim()) params.set("q", nextQuery.trim());
    const [categoryBody, mailBody] = await Promise.all([
      api<{ categories: Category[] }>("/get-categories"),
      api<{ emails: MailItem[] }>(`/emails?${params.toString()}`),
    ]);
    setCategories(categoryBody.categories);
    setEmails(mailBody.emails);
    setSelected((current) => mailBody.emails.find((item) => item.id === current?.id) ?? mailBody.emails[0] ?? null);
  }

  useEffect(() => {
    if (!user) return;
    let cancelled = false;
    const shouldFetch = pendingFetch.current;
    pendingFetch.current = false;
    (async () => {
      try {
        if (shouldFetch) {
          setBusy("Fetching mail");
          const result = await api<FetchResult>("/fetch-emails", {
            method: "POST",
            body: JSON.stringify({ limit: 50 }),
          });
          if (result.errors.length) throw new Error(result.errors.join(" "));
        }
        if (!cancelled) await refreshInbox();
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Something went wrong");
      } finally {
        if (!cancelled) setBusy("");
      }
    })();
    return () => {
      cancelled = true;
    };
    // Load once when the session becomes available. Search and category changes call refreshInbox directly.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]);

  const orderedCategories = useMemo(() => {
    return [...categories].sort(
      (a, b) => CATEGORY_ORDER.indexOf(a.slug) - CATEGORY_ORDER.indexOf(b.slug),
    );
  }, [categories]);

  async function run(label: string, action: () => Promise<void>) {
    setBusy(label);
    setError("");
    try {
      await action();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy("");
    }
  }

  async function onMailbox(event: FormEvent) {
    event.preventDefault();
    await run("Checking mailbox", async () => {
      const body = await api<{ access_token: string }>("/auth/mailbox", {
        method: "POST",
        body: JSON.stringify({
          email: mailbox.email,
          password: mailbox.password,
          host: mailbox.host.trim() || undefined,
        }),
      });
      pendingFetch.current = true;
      saveToken(body.access_token);
      setToken(body.access_token);
    });
  }

  async function onDemo(event: FormEvent) {
    event.preventDefault();
    await run("Signing in", async () => {
      const body = await api<{ access_token: string }>("/auth/dev", {
        method: "POST",
        body: JSON.stringify({ email: emailInput }),
      });
      saveToken(body.access_token);
      setToken(body.access_token);
    });
  }

  async function onGmail() {
    await run("Opening Google", async () => {
      const body = await api<{ authorization_url: string }>("/auth/google");
      window.location.href = body.authorization_url;
    });
  }

  async function onImap(event: FormEvent) {
    event.preventDefault();
    await run("Saving IMAP", async () => {
      const next = await api<SessionUser>("/auth/imap", {
        method: "POST",
        body: JSON.stringify({
          host: imap.host,
          username: imap.username,
          password: imap.password,
          port: Number(imap.port) || 993,
          use_ssl: true,
        }),
      });
      setUser(next);
      setImap({ host: "", username: "", password: "", port: "993" });
    });
  }

  function signOut() {
    clearToken();
    setToken(null);
    setUser(null);
    setEmails([]);
    setSelected(null);
  }

  if (token && !user) {
    return (
      <main className="gate">
        <section className="gate-card">
          <p className="eyebrow">Inbox sorting</p>
          <h1>Email Classifier</h1>
          <p className="hint">Loading your inbox…</p>
        </section>
      </main>
    );
  }

  if (!user) {
    return (
      <main className="gate">
        <section className="gate-card">
          <p className="eyebrow">Inbox sorting</p>
          <h1>Email Classifier</h1>
          <p className="lede">
            Sign in with the mailbox you want to read. Recent messages are fetched and sorted into Payment, Spam, Promotions, and General.
          </p>
          {error && <p className="error">{error}</p>}
          <form onSubmit={onMailbox} className="stack">
            <label>
              Email
              <input
                value={mailbox.email}
                onChange={(event) => setMailbox({ ...mailbox, email: event.target.value })}
                type="email"
                autoComplete="username"
                placeholder="you@gmail.com"
                required
              />
            </label>
            <label>
              App password
              <input
                value={mailbox.password}
                onChange={(event) => setMailbox({ ...mailbox, password: event.target.value })}
                type="password"
                autoComplete="current-password"
                required
              />
            </label>
            <label>
              Mail server
              <input
                value={mailbox.host}
                onChange={(event) => setMailbox({ ...mailbox, host: event.target.value })}
                placeholder="Optional. Gmail, Outlook, and Yahoo are detected."
              />
            </label>
            <button type="submit" disabled={Boolean(busy)}>
              {busy || "Connect and fetch mail"}
            </button>
          </form>
          <p className="hint">
            Gmail, Outlook, Yahoo, and iCloud reject the website password. Create an app password in that account’s security settings and paste it here. The app only reads mail.
          </p>
          <form onSubmit={onDemo} className="stack demo">
            <label>
              Demo account
              <input value={emailInput} onChange={(event) => setEmailInput(event.target.value)} type="email" required />
            </label>
            <button type="submit" className="secondary" disabled={Boolean(busy)}>
              Continue with sample inbox
            </button>
          </form>
          <button type="button" className="ghost" onClick={onGmail} disabled={Boolean(busy)}>
            Connect with Google instead
          </button>
        </section>
      </main>
    );
  }

  return (
    <div className="shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Email Classifier</p>
          <strong>{user.email}</strong>
        </div>
        <div className="top-actions">
          <button type="button" onClick={() => run("Fetching", async () => {
            const result = await api<FetchResult>("/fetch-emails", { method: "POST", body: JSON.stringify({ limit: 50 }) });
            if (result.errors.length) throw new Error(result.errors.join(" "));
            await refreshInbox();
          })} disabled={Boolean(busy)}>
            Fetch mail
          </button>
          <button type="button" className="secondary" onClick={() => run("Classifying", async () => { await api("/filter-emails", { method: "POST", body: JSON.stringify({}) }); await refreshInbox(); })} disabled={Boolean(busy)}>
            Reclassify
          </button>
          <button type="button" className="secondary" onClick={() => run("Loading samples", async () => { await api("/emails/import", { method: "POST", body: JSON.stringify({ messages: SAMPLES }) }); await refreshInbox("all", ""); setActive("all"); setQuery(""); })} disabled={Boolean(busy)}>
            Load samples
          </button>
          <button type="button" className="ghost" onClick={signOut}>
            Sign out
          </button>
        </div>
      </header>

      <div className="layout">
        <aside>
          <button type="button" className={active === "all" ? "nav active" : "nav"} onClick={() => { setActive("all"); refreshInbox("all", query).catch((err: Error) => setError(err.message)); }}>
            <span>All mail</span>
            <em>{orderedCategories.reduce((sum, item) => sum + item.count, 0)}</em>
          </button>
          {orderedCategories.map((category) => (
            <button
              key={category.slug}
              type="button"
              className={active === category.slug ? `nav active ${category.slug}` : `nav ${category.slug}`}
              onClick={() => {
                setActive(category.slug);
                refreshInbox(category.slug, query).catch((err: Error) => setError(err.message));
              }}
            >
              <span>{category.name}</span>
              <em>{category.count}</em>
            </button>
          ))}
          <form onSubmit={onImap} className="imap">
            <p>Add another mailbox</p>
            <input placeholder="Email" value={imap.username} onChange={(event) => setImap({ ...imap, username: event.target.value })} required />
            <input placeholder="App password" type="password" value={imap.password} onChange={(event) => setImap({ ...imap, password: event.target.value })} required />
            <input placeholder="Mail server (optional)" value={imap.host} onChange={(event) => setImap({ ...imap, host: event.target.value })} />
            <button type="submit" className="secondary" disabled={Boolean(busy)}>Save account</button>
            {user.imap_accounts.length > 0 && (
              <p className="hint">
                Connected: {user.imap_accounts.map((item) => item.username).join(", ")}
                {user.gmail_connected ? ". Gmail OAuth is also connected." : "."}
              </p>
            )}
          </form>
        </aside>

        <section className="list-pane">
          <form
            className="search"
            onSubmit={(event) => {
              event.preventDefault();
              refreshInbox(active, query).catch((err: Error) => setError(err.message));
            }}
          >
            <input
              placeholder="Search sender or subject"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
            <button type="submit" className="secondary">Search</button>
          </form>
          {error && <p className="error">{error}</p>}
          {busy && <p className="hint">{busy}</p>}
          <ul className="mail-list">
            {emails.map((item) => (
              <li key={item.id}>
                <button type="button" className={selected?.id === item.id ? "mail selected" : "mail"} onClick={() => setSelected(item)}>
                  <span className={`badge ${item.category}`}>{item.category}</span>
                  <strong>{item.subject || "(no subject)"}</strong>
                  <span className="meta">{item.sender || "Unknown sender"} · {formatWhen(item.received_at)}</span>
                  <span className="snippet">{item.snippet}</span>
                </button>
              </li>
            ))}
            {emails.length === 0 && <li className="empty">No messages in this view. Load samples or fetch mail.</li>}
          </ul>
        </section>

        <article className="reader">
          {selected ? (
            <>
              <span className={`badge ${selected.category}`}>{selected.category}</span>
              <h2>{selected.subject || "(no subject)"}</h2>
              <p className="meta">{selected.sender}</p>
              <p className="hint">
                {selected.classification_source} · {selected.provider}
                {selected.confidence != null ? ` · ${Math.round(selected.confidence * 100)}%` : ""}
              </p>
              <label>
                Move to
                <select
                  value={selected.category}
                  onChange={(event) => {
                    const category = event.target.value;
                    run("Saving label", async () => {
                      await api(`/emails/${selected.id}`, {
                        method: "PATCH",
                        body: JSON.stringify({ category }),
                      });
                      await refreshInbox();
                    });
                  }}
                >
                  {CATEGORY_ORDER.map((slug) => (
                    <option key={slug} value={slug}>{slug}</option>
                  ))}
                </select>
              </label>
              <pre>{selected.body_text}</pre>
              <button
                type="button"
                className="secondary"
                onClick={() => run("Training", async () => { await api("/filter-emails/train", { method: "POST" }); })}
                disabled={Boolean(busy)}
              >
                Train model on labeled mail
              </button>
            </>
          ) : (
            <p className="empty">Select a message.</p>
          )}
        </article>
      </div>
    </div>
  );
}
