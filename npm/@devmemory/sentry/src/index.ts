import { Event, Hint } from "@sentry/node";
import initSqlJs, { Database } from "sql.js";
import * as fs from "fs";
import * as path from "path";
import { execSync } from "child_process";

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

type BeforeSendCallback = (event: Event, hint: Hint) => Event;

let sqlJsInitialized = false;
let SQL: any = null;

function getRepoId(): string | null {
  // Try environment variable
  if (process.env.DEVMEMORY_REPO_ID) {
    return process.env.DEVMEMORY_REPO_ID;
  }

  // Try to read from .devmemory/config.json
  try {
    const configPath = path.resolve(".devmemory/config.json");
    if (fs.existsSync(configPath)) {
      const config = JSON.parse(fs.readFileSync(configPath, "utf-8"));
      if (config.namespace && config.namespace !== "non-git") {
        return config.namespace;
      }
    }
  } catch {
    // Ignore errors
  }

  // Try git remote
  try {
    const remoteUrl = execSync("git remote get-url origin", { encoding: "utf-8" }).trim();
    if (remoteUrl) {
      // Extract repo name from URL like https://github.com/user/repo.git
      const match = remoteUrl.match(/([^/]+)\.git$/);
      if (match) {
        return match[1];
      }
      // Or from SSH like git@github.com:user/repo.git
      const sshMatch = remoteUrl.match(/:([^/]+)\.git$/);
      if (sshMatch) {
        return sshMatch[1];
      }
    }
  } catch {
    // Ignore errors
  }

  return null;
}

function getSqlitePath(): string {
  // Try environment variable
  if (process.env.DEVMEMORY_SQLITE_PATH) {
    return process.env.DEVMEMORY_SQLITE_PATH;
  }

  // Try config file
  try {
    const configPath = path.resolve(".devmemory/config.json");
    if (fs.existsSync(configPath)) {
      const config = JSON.parse(fs.readFileSync(configPath, "utf-8"));
      if (config.sqlite_path) {
        return config.sqlite_path;
      }
    }
  } catch {
    // Ignore errors
  }

  // Default path
  return ".devmemory/attributions.db";
}

function getMode(): "local" | "cloud" {
  if (process.env.DEVMEMORY_MODE === "cloud") {
    return "cloud";
  }
  return "local";
}

async function initSqlJsOnce(): Promise<any> {
  if (!sqlJsInitialized) {
    SQL = await initSqlJs();
    sqlJsInitialized = true;
  }
  return SQL;
}

function extractFirstInAppFrame(event: Event): any | null {
  const exception = event.exception;
  if (exception && exception.values) {
    for (const exc of exception.values) {
      const stacktrace = exc.stacktrace;
      if (stacktrace && stacktrace.frames) {
        for (const frame of stacktrace.frames) {
          if (frame.in_app) {
            return frame;
          }
        }
      }
    }
  }

  const threads = event.threads;
  if (threads && threads.values) {
    for (const thread of threads.values) {
      const stacktrace = thread.stacktrace;
      if (stacktrace && stacktrace.frames) {
        for (const frame of stacktrace.frames) {
          if (frame.in_app) {
            return frame;
          }
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
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        repo_id: repoId,
        filepath: filepath,
        lineno: lineno,
      }),
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    if (response.ok) {
      return await response.json();
    }
    return null;
  } catch {
    return null;
  }
}

function lookupFromLocal(
  db: Database,
  _namespace: string,
  filepath: string,
  lineno: number
): Attribution | null {
  try {
    // Normalize filepath - remove leading ./ or /
    const normalizedPath = filepath.replace(/^\.?\/?/, "");

    // Query for attribution matching the file and line
    // The attributions table has line_ranges JSON storing ranges like "1-45": {...}
    const stmt = db.prepare(`
      SELECT author, author_email, tool, model, prompt_id, commit_sha, line_ranges
      FROM attributions
      WHERE namespace = ? AND filepath = ?
      ORDER BY commit_timestamp DESC
      LIMIT 1
    `);

    stmt.bind([_namespace, normalizedPath]);

    if (stmt.step()) {
      const row = stmt.getAsObject() as any;
      stmt.free();

      const lineRanges = row.line_ranges;
      if (lineRanges && typeof lineRanges === "object") {
        // Find which range contains our line number
        for (const [rangeKey, data] of Object.entries(lineRanges)) {
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

      // If no line range matched but we have a row, return basic info
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

    stmt.free();
    return null;
  } catch (error) {
    console.warn("[DevMemory] SQLite lookup error:", error);
    return null;
  }
}

let cachedDb: Database | null = null;
let cachedDbPath: string | null = null;

async function getDatabase(sqlitePath: string): Promise<Database | null> {
  // Return cached db if same path
  if (cachedDb && cachedDbPath === sqlitePath) {
    return cachedDb;
  }

  // Close old db if different path
  if (cachedDb && cachedDbPath !== sqlitePath) {
    cachedDb.close();
    cachedDb = null;
  }

  try {
    const fullPath = path.resolve(sqlitePath);

    if (!fs.existsSync(fullPath)) {
      console.warn(`[DevMemory] SQLite database not found at: ${fullPath}`);
      return null;
    }

    const buffer = fs.readFileSync(fullPath);
    const SQL = await initSqlJsOnce();
    cachedDb = new SQL.Database(buffer);
    cachedDbPath = sqlitePath;

    return cachedDb;
  } catch (error) {
    console.warn("[DevMemory] Failed to open SQLite database:", error);
    return null;
  }
}

export function createDevMemoryBeforeSend(
  options: DevMemoryOptions = {}
): BeforeSendCallback {
  // Apply defaults with auto-detection
  const mode = options.mode || getMode();
  const repoId = options.repoId || getRepoId();
  const sqlitePath = options.sqlitePath || getSqlitePath();
  const apiUrl = options.apiUrl || process.env.DEVMEMORY_API_URL;
  const timeout = options.timeout || 2000;

  // Pre-load database for local mode
  let dbPromise: Promise<Database | null> | null = null;
  if (mode === "local") {
    dbPromise = getDatabase(sqlitePath);
  }

  return async function beforeSend(
    event: Event,
    _hint: Hint
  ): Promise<Event> {
    // Check if repoId is available
    if (!repoId) {
      console.warn("[DevMemory] repoId not found. Set DEVMEMORY_REPO_ID env var or run devmemory install.");
      return event;
    }

    try {
      const frame = extractFirstInAppFrame(event);
      if (!frame) {
        return event;
      }

      const filepath = frame.filename || frame.abs_path || "";
      const lineno = frame.lineno;

      if (!filepath || !lineno) {
        return event;
      }

      let attribution: Attribution | null = null;

      if (mode === "cloud") {
        if (!apiUrl) {
          console.warn(
            "[DevMemory] Cloud mode requires apiUrl. Set mode: 'local' for offline mode."
          );
          return event;
        }
        attribution = await lookupFromAPI(apiUrl, repoId, filepath, lineno, timeout);
      } else {
        // Local mode - read from SQLite
        if (!dbPromise) {
          dbPromise = getDatabase(sqlitePath);
        }

        const db = await dbPromise;
        if (db) {
          attribution = lookupFromLocal(db, repoId, filepath, lineno);
        } else {
          console.warn(
            `[DevMemory] Could not open SQLite database at: ${sqlitePath}`
          );
        }
      }

      if (attribution && attribution.author) {
        event.tags = event.tags || {};
        event.tags["ai_origin"] = attribution.author || "unknown";
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
      // Silently fail - don't break Sentry
    }

    return event;
  };
}

export default createDevMemoryBeforeSend;
