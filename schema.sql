-- Email classifier schema for Supabase (PostgreSQL 15+).
-- Paste this file into the Supabase SQL Editor and run it once.
-- Users own connected accounts, stored messages, and optional private rules.
-- Global rules use rules.user_id IS NULL.

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email         VARCHAR(320) NOT NULL UNIQUE,
    name          VARCHAR(200),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at    TIMESTAMPTZ
);

CREATE TABLE oauth_credentials (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id            UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider           VARCHAR(32) NOT NULL,
    access_token_enc   TEXT NOT NULL,
    refresh_token_enc  TEXT,
    token_expiry       TIMESTAMPTZ,
    scopes             TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, provider)
);

CREATE TABLE imap_accounts (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    host           VARCHAR(255) NOT NULL,
    port           INTEGER NOT NULL DEFAULT 993,
    username       VARCHAR(320) NOT NULL,
    password_enc   TEXT NOT NULL,
    use_ssl        BOOLEAN NOT NULL DEFAULT TRUE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, host, username)
);

CREATE TABLE categories (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug         VARCHAR(64) NOT NULL UNIQUE,
    name         VARCHAR(100) NOT NULL,
    description  TEXT,
    CONSTRAINT categories_slug_check CHECK (slug IN ('payment', 'spam', 'promotions', 'general'))
);

CREATE TABLE emails (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id               UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider              VARCHAR(32) NOT NULL,
    provider_message_id   VARCHAR(255) NOT NULL,
    thread_id             VARCHAR(255),
    sender                VARCHAR(500),
    recipients            TEXT,
    subject               TEXT,
    snippet               TEXT,
    body_text             TEXT,
    received_at           TIMESTAMPTZ,
    category_id           UUID REFERENCES categories(id),
    confidence            DOUBLE PRECISION,
    classification_source VARCHAR(16),
    headers               JSONB,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, provider, provider_message_id)
);

CREATE INDEX emails_user_category_idx ON emails (user_id, category_id);
CREATE INDEX emails_user_received_idx ON emails (user_id, received_at DESC);

CREATE TABLE rules (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID REFERENCES users(id) ON DELETE CASCADE,
    category_id  UUID NOT NULL REFERENCES categories(id),
    field        VARCHAR(16) NOT NULL,
    operator     VARCHAR(16) NOT NULL,
    pattern      TEXT NOT NULL,
    priority     INTEGER NOT NULL DEFAULT 0,
    enabled      BOOLEAN NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT rules_field_check CHECK (field IN ('subject', 'sender', 'body', 'any')),
    CONSTRAINT rules_operator_check CHECK (operator IN ('contains', 'equals', 'regex'))
);

CREATE INDEX rules_priority_idx ON rules (enabled, priority DESC);

CREATE TABLE classification_models (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    version      VARCHAR(64) NOT NULL UNIQUE,
    artifact_path TEXT NOT NULL,
    metrics      JSONB,
    trained_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_active    BOOLEAN NOT NULL DEFAULT FALSE
);
