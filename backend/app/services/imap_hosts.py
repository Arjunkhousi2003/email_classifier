"""Map an email address to the IMAP server that accepts a password login."""

from app.services.errors import ProviderError

# Providers that accept an app password over IMAP. The account password used
# on the website is rejected by Gmail, Outlook, and Yahoo.
KNOWN_HOSTS = {
    "gmail.com": "imap.gmail.com",
    "googlemail.com": "imap.gmail.com",
    "outlook.com": "outlook.office365.com",
    "hotmail.com": "outlook.office365.com",
    "live.com": "outlook.office365.com",
    "msn.com": "outlook.office365.com",
    "yahoo.com": "imap.mail.yahoo.com",
    "ymail.com": "imap.mail.yahoo.com",
    "rocketmail.com": "imap.mail.yahoo.com",
    "icloud.com": "imap.mail.me.com",
    "me.com": "imap.mail.me.com",
    "mac.com": "imap.mail.me.com",
    "aol.com": "imap.aol.com",
    "zoho.com": "imap.zoho.com",
    "zoho.in": "imap.zoho.in",
    "gmx.com": "imap.gmx.com",
    "gmx.net": "imap.gmx.net",
    "fastmail.com": "imap.fastmail.com",
}

APP_PASSWORD_DOMAINS = {
    "gmail.com",
    "googlemail.com",
    "outlook.com",
    "hotmail.com",
    "live.com",
    "msn.com",
    "yahoo.com",
    "ymail.com",
    "rocketmail.com",
    "icloud.com",
    "me.com",
    "mac.com",
}


def email_domain(address: str) -> str:
    domain = address.strip().lower().rsplit("@", 1)[-1]
    if not domain or "." not in domain:
        raise ProviderError("Enter a full email address such as name@gmail.com")
    return domain


def resolve_imap_host(address: str) -> str:
    domain = email_domain(address)
    if domain in {"proton.me", "protonmail.com", "pm.me"}:
        raise ProviderError(
            "Proton Mail does not accept an email and password over IMAP. Use Proton Bridge, then enter host 127.0.0.1."
        )
    if domain in KNOWN_HOSTS:
        return KNOWN_HOSTS[domain]
    if domain.startswith("yahoo."):
        return "imap.mail.yahoo.com"
    return f"imap.{domain}"


def normalize_mailbox_password(password: str) -> str:
    cleaned = password.strip()
    compact = cleaned.replace(" ", "")
    # Gmail shows app passwords as four groups of four characters.
    if " " in cleaned and len(compact) == 16 and compact.isalnum():
        return compact
    return cleaned


def needs_app_password(address: str) -> bool:
    domain = email_domain(address)
    return domain in APP_PASSWORD_DOMAINS or domain.startswith("yahoo.")
