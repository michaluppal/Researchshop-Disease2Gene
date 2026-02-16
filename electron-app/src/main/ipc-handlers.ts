import { ipcMain, app, safeStorage, dialog, BrowserWindow } from "electron";
import { spawn, type ChildProcess } from "node:child_process";
import fs from "node:fs/promises";
import path from "node:path";
import Store from "electron-store";
import type { PipelineConfig, ProgressData, ResultData, ErrorData } from "./types.js";

const store = new Store<Record<string, unknown>>({ name: "disease2gene" });

/** Currently running pipeline child process. */
let pipelineProcess: ChildProcess | null = null;

/** Resolve the path to the Python modules directory. */
function getModulesPath(): string {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, "modules");
  }
  // Development: modules are at the repo root
  return path.join(app.getAppPath(), "..", "..", "modules");
}

/** Get the path to the repo root (parent of electron-app). */
function getRepoRoot(): string {
  if (app.isPackaged) {
    return process.resourcesPath;
  }
  return path.join(app.getAppPath(), "..", "..");
}

/** Send data to the focused renderer window. */
function sendToRenderer(channel: string, data: unknown): void {
  const windows = BrowserWindow.getAllWindows();
  const target = windows[0];
  if (target && !target.isDestroyed()) {
    target.webContents.send(channel, data);
  }
}

// ---------------------------------------------------------------------------
// API Key handlers (safeStorage + electron-store)
// ---------------------------------------------------------------------------

function registerApiKeyHandlers(): void {
  ipcMain.handle(
    "api-key:save",
    async (_event, provider: string, key: string): Promise<void> => {
      if (!safeStorage.isEncryptionAvailable()) {
        throw new Error("Encryption is not available on this system");
      }
      const encrypted = safeStorage.encryptString(key);
      store.set(`apiKeys.${provider}`, encrypted.toString("base64"));
    }
  );

  ipcMain.handle(
    "api-key:get",
    async (_event, provider: string): Promise<string> => {
      const stored = store.get(`apiKeys.${provider}`) as string | undefined;
      if (!stored) {
        return "";
      }
      if (!safeStorage.isEncryptionAvailable()) {
        throw new Error("Encryption is not available on this system");
      }
      const buffer = Buffer.from(stored, "base64");
      return safeStorage.decryptString(buffer);
    }
  );

  ipcMain.handle(
    "api-key:delete",
    async (_event, provider: string): Promise<void> => {
      store.delete(`apiKeys.${provider}`);
    }
  );

  ipcMain.handle("api-key:list-providers", async (): Promise<string[]> => {
    const apiKeys = store.get("apiKeys") as Record<string, unknown> | undefined;
    if (!apiKeys || typeof apiKeys !== "object") {
      return [];
    }
    return Object.keys(apiKeys);
  });
}

// ---------------------------------------------------------------------------
// Pipeline handlers
// ---------------------------------------------------------------------------

function registerPipelineHandlers(): void {
  ipcMain.handle(
    "pipeline:run",
    async (_event, config: PipelineConfig): Promise<void> => {
      if (pipelineProcess) {
        throw new Error("A pipeline is already running");
      }

      const repoRoot = getRepoRoot();
      const pythonScript = path.join(getModulesPath(), "pipeline_orchestrator.py");

      // Build the config JSON to pass via stdin
      const pipelineInput = JSON.stringify({
        query: config.query,
        specific_pmids: config.specificPmids,
        specific_authors: config.specificAuthors,
        user_columns: config.userColumns.map((col) => ({
          name: col.name,
          description: col.description,
        })),
        top_n_cited: config.topNCited,
        max_results: config.maxResults,
      });

      // Build environment variables for the child process
      const env: Record<string, string> = {
        ...process.env as Record<string, string>,
        GEMINI_API_KEY: config.geminiApiKey,
        ENTREZ_EMAIL: config.entrezEmail,
        PYTHONPATH: repoRoot,
        PYTHONUNBUFFERED: "1",
      };

      if (config.entrezApiKey) {
        env.ENTREZ_API_KEY = config.entrezApiKey;
      }
      if (config.outputDir) {
        env.OUTPUT_DIR = config.outputDir;
      }

      // Spawn the Python pipeline as a child process.
      // We use a small wrapper invocation so the orchestrator reads JSON from stdin.
      pipelineProcess = spawn(
        "python3",
        [
          "-c",
          [
            "import sys, json",
            "from modules.pipeline_orchestrator import run_complete_pipeline",
            "cfg = json.loads(sys.stdin.read())",
            "def progress_cb(stage, pct):",
            '    print(json.dumps({"type":"progress","stage":stage,"percent":pct}), flush=True)',
            "result = run_complete_pipeline(",
            "    query=cfg['query'],",
            "    specific_pmids=cfg.get('specific_pmids', []),",
            "    specific_authors=cfg.get('specific_authors', []),",
            "    user_columns=cfg.get('user_columns', []),",
            "    top_n_cited=cfg.get('top_n_cited', 10),",
            "    max_results=cfg.get('max_results'),",
            "    progress_callback=progress_cb,",
            ")",
            'print(json.dumps({"type":"result","data":result}), flush=True)',
          ].join("\n"),
        ],
        { cwd: repoRoot, env, stdio: ["pipe", "pipe", "pipe"] }
      );

      // Write config to stdin and close
      pipelineProcess.stdin?.write(pipelineInput);
      pipelineProcess.stdin?.end();

      // Stream stdout for progress and result messages
      let stdoutBuffer = "";
      pipelineProcess.stdout?.on("data", (chunk: Buffer) => {
        stdoutBuffer += chunk.toString();
        const lines = stdoutBuffer.split("\n");
        // Keep the last (possibly incomplete) line in the buffer
        stdoutBuffer = lines.pop() ?? "";

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed) continue;
          try {
            const msg = JSON.parse(trimmed) as Record<string, unknown>;
            if (msg.type === "progress") {
              const progress: ProgressData = {
                stage: msg.stage as string,
                percent: msg.percent as number,
                message: `${msg.stage as string} (${msg.percent as number}%)`,
              };
              sendToRenderer("pipeline:progress", progress);
            } else if (msg.type === "result") {
              const data = msg.data as Record<string, unknown> | null;
              const result: ResultData = {
                outputPath: (data?.output_path as string) ?? "",
                totalPapers: (data?.total_papers as number) ?? 0,
                totalGenes: (data?.total_genes as number) ?? 0,
                records: (data?.records as Record<string, unknown>[]) ?? [],
              };
              sendToRenderer("pipeline:result", result);
            }
          } catch {
            // Non-JSON lines are regular log output — ignore
          }
        }
      });

      // Capture stderr for error reporting
      let stderrOutput = "";
      pipelineProcess.stderr?.on("data", (chunk: Buffer) => {
        stderrOutput += chunk.toString();
      });

      pipelineProcess.on("close", (code) => {
        if (code !== 0 && code !== null) {
          const error: ErrorData = {
            message: `Pipeline exited with code ${code}`,
            details: stderrOutput.slice(-2000),
          };
          sendToRenderer("pipeline:error", error);
        }
        pipelineProcess = null;
      });

      pipelineProcess.on("error", (err) => {
        const error: ErrorData = {
          message: `Failed to start pipeline: ${err.message}`,
        };
        sendToRenderer("pipeline:error", error);
        pipelineProcess = null;
      });
    }
  );

  ipcMain.handle("pipeline:stop", async (): Promise<void> => {
    if (!pipelineProcess) {
      return;
    }
    // Send SIGTERM for graceful shutdown (the orchestrator handles signals)
    pipelineProcess.kill("SIGTERM");

    // Force kill after 10 seconds if still running
    const forceKillTimer = setTimeout(() => {
      if (pipelineProcess && !pipelineProcess.killed) {
        pipelineProcess.kill("SIGKILL");
      }
    }, 10_000);

    pipelineProcess.on("close", () => {
      clearTimeout(forceKillTimer);
      pipelineProcess = null;
    });
  });
}

// ---------------------------------------------------------------------------
// Results export
// ---------------------------------------------------------------------------

function registerExportHandlers(): void {
  ipcMain.handle(
    "results:export",
    async (_event, format: "csv" | "json", data: unknown): Promise<string> => {
      const extension = format === "csv" ? "csv" : "json";
      const filters =
        format === "csv"
          ? [{ name: "CSV Files", extensions: ["csv"] }]
          : [{ name: "JSON Files", extensions: ["json"] }];

      const { canceled, filePath } = await dialog.showSaveDialog({
        title: "Export Results",
        defaultPath: `disease2gene_results.${extension}`,
        filters,
      });

      if (canceled || !filePath) {
        return "";
      }

      let content: string;
      if (format === "json") {
        content = JSON.stringify(data, null, 2);
      } else {
        // Convert array of records to CSV
        const records = data as Record<string, unknown>[];
        if (!Array.isArray(records) || records.length === 0) {
          content = "";
        } else {
          const headers = Object.keys(records[0]);
          const csvRows = [headers.join(",")];
          for (const record of records) {
            const values = headers.map((h) => {
              const val = String(record[h] ?? "");
              // Escape CSV values that contain commas, quotes, or newlines
              if (val.includes(",") || val.includes('"') || val.includes("\n")) {
                return `"${val.replace(/"/g, '""')}"`;
              }
              return val;
            });
            csvRows.push(values.join(","));
          }
          content = csvRows.join("\n");
        }
      }

      await fs.writeFile(filePath, content, "utf-8");
      return filePath;
    }
  );
}

// ---------------------------------------------------------------------------
// Settings
// ---------------------------------------------------------------------------

function registerSettingsHandlers(): void {
  ipcMain.handle("settings:get", async (): Promise<Record<string, unknown>> => {
    const settings = store.get("settings") as Record<string, unknown> | undefined;
    return settings ?? {};
  });

  ipcMain.handle(
    "settings:save",
    async (_event, settings: Record<string, unknown>): Promise<void> => {
      store.set("settings", settings);
    }
  );
}

// ---------------------------------------------------------------------------
// PubMed search (delegates to the Python module)
// ---------------------------------------------------------------------------

function registerPubMedHandlers(): void {
  ipcMain.handle(
    "pubmed:search",
    async (_event, query: string, maxResults: number): Promise<unknown[]> => {
      const repoRoot = getRepoRoot();

      // Retrieve entrez email from settings
      const settings = store.get("settings") as Record<string, unknown> | undefined;
      const entrezEmail = (settings?.entrezEmail as string) ?? "";

      return new Promise((resolve, reject) => {
        const child = spawn(
          "python3",
          [
            "-c",
            [
              "import sys, json",
              "from modules.pubmed_data_collector import search_pubmed, fetch_details",
              `from modules import config`,
              `config.ENTREZ_EMAIL = ${JSON.stringify(entrezEmail)}`,
              `pmids = search_pubmed(${JSON.stringify(query)}, max_results=${maxResults})`,
              "details = fetch_details(pmids)",
              "print(json.dumps(details, default=str))",
            ].join("\n"),
          ],
          {
            cwd: repoRoot,
            env: {
              ...process.env as Record<string, string>,
              PYTHONPATH: repoRoot,
              PYTHONUNBUFFERED: "1",
            },
            stdio: ["ignore", "pipe", "pipe"],
          }
        );

        let stdout = "";
        let stderr = "";
        child.stdout?.on("data", (chunk: Buffer) => {
          stdout += chunk.toString();
        });
        child.stderr?.on("data", (chunk: Buffer) => {
          stderr += chunk.toString();
        });

        child.on("close", (code) => {
          if (code !== 0) {
            reject(new Error(`PubMed search failed (exit ${code}): ${stderr.slice(-1000)}`));
            return;
          }
          try {
            // Take the last JSON line (skip any log output before it)
            const lines = stdout.trim().split("\n");
            const lastLine = lines[lines.length - 1];
            const results = JSON.parse(lastLine) as unknown[];
            resolve(results);
          } catch (parseErr) {
            reject(new Error(`Failed to parse PubMed results: ${String(parseErr)}`));
          }
        });

        child.on("error", (err) => {
          reject(new Error(`Failed to spawn PubMed search: ${err.message}`));
        });
      });
    }
  );
}

// ---------------------------------------------------------------------------
// App info
// ---------------------------------------------------------------------------

function registerAppInfoHandlers(): void {
  ipcMain.handle("app:version", async (): Promise<string> => {
    return app.getVersion();
  });
}

// ---------------------------------------------------------------------------
// Register all handlers
// ---------------------------------------------------------------------------

export function registerIpcHandlers(): void {
  registerApiKeyHandlers();
  registerPipelineHandlers();
  registerExportHandlers();
  registerSettingsHandlers();
  registerPubMedHandlers();
  registerAppInfoHandlers();
}
