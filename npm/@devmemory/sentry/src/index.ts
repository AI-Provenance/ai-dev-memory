import { Event } from "@sentry/node";

export interface DevMemoryOptions {
  repoId?: string;
  mode?: "local" | "cloud";
  apiUrl?: string;
  sqlitePath?: string;
  timeout?: number;
}

export interface Attribution {
  author: string;
  author_email?: string;
  tool?: string;
  model?: string;
  prompt_id?: string;
  confidence?: number;
  commit_sha?: string;
  filepath?: string;
  lineno?: number;
}

let repoIdCache: string | null | undefined;

function getRepoId(): string | null {
  if (repoIdCache !== undefined) return repoIdCache;

  if (process.env.DEVMEMORY_REPO_ID) {
    repoIdCache = process.env.DEVMEMORY_REPO_ID;
    return repoIdCache;
  }

  try {
    const fs = require("fs");
    const path = require("path");
    const configPath = path.resolve(".devmemory/config.json");
    if (fs.existsSync(configPath)) {
      const config = JSON.parse(fs.readFileSync(configPath, "utf-8"));
      if (config.namespace && config.namespace !== "non-git") {
        repoIdCache = config.namespace;
        return config.namespace;
      }
    }
  } catch {}

  repoIdCache = null;
  return null;
}

function getSqlitePath(): string {
  if (process.env.DEVMEMORY_SQLITE_PATH) {
    return process.env.DEVMEMORY_SQLITE_PATH;
  }

  try {
    const fs = require("fs");
    const path = require("path");
    const configPath = path.resolve(".devmemory/config.json");
    if (fs.existsSync(configPath)) {
      const config = JSON.parse(fs.readFileSync(configPath, "utf-8"));
      if (config.sqlite_path) {
        // Validate path is within current repo
        try {
          const normalized = path.resolve(config.sqlite_path);
          const cwd = process.cwd();
          if (normalized.startsWith(cwd)) {
            return config.sqlite_path;
          }
        } catch {}
      }
    }
  } catch {}

  return ".devmemory/attributions.db";
}

function getMode(): "local" | "cloud" {
  if (process.env.DEVMEMORY_MODE === "cloud") return "cloud";
  return "local";
}

function extractFirstInAppFrame(event: Event): any | null {
  const exception = event.exception;
  if (exception?.values) {
    for (const exc of exception.values) {
      const frames = exc.stacktrace?.frames;
      if (frames) {
        for (const frame of frames) {
          if (frame.in_app) return frame;
        }
      }
    }
  }

  const threads = event.threads;
  if (threads?.values) {
    for (const thread of threads.values) {
      const frames = thread.stacktrace?.frames;
      if (frames) {
        for (const frame of frames) {
          if (frame.in_app) return frame;
        }
      }
    }
  }

  return null;
}

async function lookupFromAPI(
  apiUrl: string,
  repoId: string,
  filepath: string,
  lineno: number,
  timeout: number
): Promise<Attribution | null> {
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);

    const response = await fetch(`${apiUrl}/api/v1/attribution/lookup`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        repo_id: repoId,
        filepath: filepath,
        lineno: lineno,
      }),
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    if (response.ok) {
      return (await response.json()) as Attribution;
    }
    return null;
  } catch {
    return null;
  }
}

function lookupFromLocal(
  sqlitePath: string,
  namespace: string,
  filepath: string,
  lineno: number
): Attribution | null {
  let db: any = null;
  try {
    const Database = require("better-sqlite3");
    const path = require("path");
    const fs = require("fs");
    const fullPath = path.resolve(sqlitePath);

    if (!fs.existsSync(fullPath)) return null;

    db = new Database(fullPath, { readonly: true, fileMustExist: true });

    const normalizedPath = filepath.replace(/^\.?\/?/, "");

    const row = db
      .prepare(
        `SELECT author, author_email, tool, model, prompt_id, commit_sha, line_ranges
         FROM attributions
         WHERE namespace = ? AND filepath = ?
         ORDER BY commit_timestamp DESC
         LIMIT 1`
      )
      .get(namespace, normalizedPath);

    if (!row) return null;

    const lineRanges = row.line_ranges;
    if (lineRanges && typeof lineRanges === "object") {
      for (const [rangeKey] of Object.entries(lineRanges)) {
        const [startStr, endStr] = rangeKey.split("-");
        const start = parseInt(startStr, 10);
        const end = parseInt(endStr, 10);

        if (lineno >= start && lineno <= end) {
          return {
            author: row.author || "ai",
            author_email: row.author_email,
            tool: row.tool,
            model: row.model,
            prompt_id: row.prompt_id,
            commit_sha: row.commit_sha,
            filepath: normalizedPath,
            lineno: lineno,
          };
        }
      }
    }

    return {
      author: row.author || "ai",
      author_email: row.author_email,
      tool: row.tool,
      model: row.model,
      prompt_id: row.prompt_id,
      commit_sha: row.commit_sha,
      filepath: normalizedPath,
      lineno: lineno,
    };
  } catch (error: any) {
    if (error?.code === "MODULE_NOT_FOUND") {
      console.warn("[DevMemory] better-sqlite3 not installed. Run: npm install better-sqlite3");
    }
    return null;
  } finally {
    if (db) {
      try {
        db.close();
      } catch {}
    }
  }
}

export function createDevMemoryBeforeSend(options: DevMemoryOptions = {}) {
  const mode = options.mode || getMode();
  const repoId = options.repoId || getRepoId();
  const sqlitePath = options.sqlitePath || getSqlitePath();
  const apiUrl = options.apiUrl || process.env.DEVMEMORY_API_URL;
  const timeout = options.timeout || 2000;

  return async function beforeSend(event: Event): Promise<Event> {
    if (!repoId) return event;

    try {
      const frame = extractFirstInAppFrame(event);
      if (!frame) return event;

      const filepath = frame.filename || frame.abs_path || "";
      const lineno = frame.lineno;

      if (!filepath || !lineno) return event;

      let attribution: Attribution | null = null;

      if (mode === "cloud") {
        if (apiUrl) {
          attribution = await lookupFromAPI(apiUrl, repoId, filepath, lineno, timeout);
        }
      } else {
        attribution = lookupFromLocal(sqlitePath, repoId, filepath, lineno);
      }

      if (attribution?.author) {
        event.tags = event.tags || {};
        event.tags["ai_origin"] = attribution.author;
        event.tags["ai_tool"] = attribution.tool || "unknown";
        event.tags["ai_model"] = attribution.model || "unknown";

        if (attribution.confidence) {
          event.tags["ai_confidence"] = attribution.confidence;
        }
        if (attribution.prompt_id) {
          event.tags["ai_prompt_id"] = attribution.prompt_id;
        }
        if (attribution.author_email) {
          event.tags["ai_author_email"] = attribution.author_email;
        }

        event.contexts = event.contexts || {};
        event.contexts["ai_attribution"] = {
          author: attribution.author,
          author_email: attribution.author_email,
          tool: attribution.tool,
          model: attribution.model,
          prompt_id: attribution.prompt_id,
          confidence: attribution.confidence,
          commit_sha: attribution.commit_sha,
          filepath: filepath,
          lineno: lineno,
          mode: mode,
        };
      }
    } catch {
      // Silently fail
    }

    return event;
  };
}

export default createDevMemoryBeforeSend;
