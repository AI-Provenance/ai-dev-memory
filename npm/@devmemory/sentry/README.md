# @devmemory/sentry

**Sentry integration for AI code attribution.**

## Install

```bash
npm install @devmemory/sentry
# or
yarn add @devmemory/sentry
```

## Quick Start (Local Mode)

```typescript
import * as Sentry from "@sentry/node";
import { createDevMemoryBeforeSend } from "@devmemory/sentry";

Sentry.init({
  dsn: process.env.SENTRY_DSN,
  beforeSend(event, hint) {
    return createDevMemoryBeforeSend({
      repoId: "my-app",
      mode: "local",
      sqlitePath: ".devmemory/attributions.db",
    })(event, hint);
  },
});
```

That's it! No external services needed.

## Options

| Option | Type | Required | Description |
|--------|------|----------|-------------|
| `repoId` | string | Yes | Your repository/namespace ID |
| `mode` | `"local"` \| `"cloud"` | Yes | Local (SQLite) or Cloud (AMS) |
| `apiUrl` | string | No* | AMS API URL (*required for cloud mode) |
| `sqlitePath` | string | No | Path to SQLite file (default: `.devmemory/attributions.db`) |
| `timeout` | number | No | Request timeout in ms (default: 2000) |

## What You Get

Every Sentry error includes:

```
Tags:
  ai_tool: cursor
  ai_model: gpt-4o
  ai_origin: ai

Contexts:
  ai_attribution:
    author: ai
    tool: cursor
    model: gpt-4o
    filepath: src/auth/login.ts
    lineno: 42
```

## Local vs Cloud

| Mode | Storage | Use Case |
|------|---------|----------|
| `local` | SQLite file | Development, no external services |
| `cloud` | AMS API | Production, team shared data |

## Setup

### 1. Install DevMemory CLI

```bash
pip install devmemory
devmemory install --mode local
```

### 2. Add Sentry Integration

```typescript
// sentry.client.config.ts
import * as Sentry from "@sentry/nextjs";
import { createDevMemoryBeforeSend } from "@devmemory/sentry";

Sentry.init({
  dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
  beforeSend(event, hint) {
    return createDevMemoryBeforeSend({
      repoId: "my-nextjs-app",
      mode: "local", // works offline!
      sqlitePath: ".devmemory/attributions.db",
    })(event, hint);
  },
});
```

## License

MIT
