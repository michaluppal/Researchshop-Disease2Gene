/**
 * Pipeline Runner Service — spawns the Disease2Gene Python pipeline
 * as a child process and streams progress/results back via IPC.
 */

import { spawn, type ChildProcess } from "node:child_process";
import path from "node:path";
import { app, BrowserWindow } from "electron";
import type { PipelineConfig, ProgressData, ResultData, ErrorData } from "../types.js";
import { logger } from "./logger-service.js";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type ProgressCallback = (data: ProgressData) => void;
type ResultCallback = (data: ResultData) => void;
type ErrorCallback = (data: ErrorData) => void;

interface PipelineMessage {
  type: "progress" | "result" | "error";
  stage?: string;
  pct?: number;
  message?: string;
  data?: Record<string, unknown>;
  papersProcessed?: number;
  papersTotal?: number;
}

// ---------------------------------------------------------------------------
// Pipeline Runner
// ---------------------------------------------------------------------------

let childProcess: ChildProcess | null = null;
let running = false;

function getProjectRoot(): string {
  if (app.isPackaged) {
    // In packaged app, resources are next to the asar
    return path.join(process.resourcesPath, "app");
  }
  // In development, go up from electron-app/dist/main/ to repo root
  return path.resolve(app.getAppPath(), "..", "..");
}

function getScriptPath(): string {
  const root = getProjectRoot();
  return path.join(root, "electron-app", "scripts", "run_pipeline.py");
}

function findPython(): string {
  // Prefer python3, fall back to python
  return process.platform === "win32" ? "python" : "python3";
}

function sendToRenderer(channel: string, data: unknown): void {
  const windows = BrowserWindow.getAllWindows();
  for (const win of windows) {
    if (!win.isDestroyed()) {
      win.webContents.send(channel, data);
    }
  }
}

export function startPipeline(
  config: PipelineConfig,
  onProgress?: ProgressCallback,
  onResult?: ResultCallback,
  onError?: ErrorCallback,
): void {
  if (running) {
    const msg = "Pipeline is already running";
    logger.warn(msg, "PipelineRunner");
    onError?.({ message: msg });
    return;
  }

  running = true;
  const scriptPath = getScriptPath();
  const pythonBin = findPython();

  logger.info(`Spawning pipeline: ${pythonBin} ${scriptPath}`, "PipelineRunner");

  const env: Record<string, string> = {
    ...process.env as Record<string, string>,
    PYTHONUNBUFFERED: "1",
    GEMINI_API_KEY: config.geminiApiKey,
    ENTREZ_EMAIL: config.entrezEmail,
  };

  if (config.entrezApiKey) {
    env.ENTREZ_API_KEY = config.entrezApiKey;
  }
  if (config.outputDir) {
    env.OUTPUT_DIR = config.outputDir;
  }

  childProcess = spawn(pythonBin, [scriptPath], {
    cwd: getProjectRoot(),
    env,
    stdio: ["pipe", "pipe", "pipe"],
  });

  // Send config as JSON via stdin
  const configPayload: Record<string, unknown> = {
    query: config.query,
    pmids: config.specificPmids,
    authors: config.specificAuthors,
    userColumns: config.userColumns,
    topNCited: config.topNCited,
    maxResults: config.maxResults,
    geminiApiKey: config.geminiApiKey,
    entrezEmail: config.entrezEmail,
    entrezApiKey: config.entrezApiKey ?? "",
    outputDir: config.outputDir ?? "",
  };

  childProcess.stdin?.write(JSON.stringify(configPayload));
  childProcess.stdin?.end();

  // Parse stdout line-by-line for JSON messages
  let stdoutBuffer = "";

  childProcess.stdout?.on("data", (chunk: Buffer) => {
    stdoutBuffer += chunk.toString("utf-8");
    const lines = stdoutBuffer.split("\n");
    // Keep the last (possibly incomplete) line in the buffer
    stdoutBuffer = lines.pop() ?? "";

    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) continue;

      let msg: PipelineMessage;
      try {
        msg = JSON.parse(trimmed) as PipelineMessage;
      } catch {
        // Non-JSON output — log it
        logger.debug(`Pipeline stdout: ${trimmed}`, "PipelineRunner");
        continue;
      }

      switch (msg.type) {
        case "progress": {
          const progressData: ProgressData = {
            stage: msg.stage ?? "unknown",
            percent: msg.pct ?? 0,
            message: msg.message ?? msg.stage ?? "",
            papersProcessed: msg.papersProcessed,
            papersTotal: msg.papersTotal,
          };
          sendToRenderer("pipeline:progress", progressData);
          onProgress?.(progressData);
          break;
        }
        case "result": {
          const resultData = msg.data as unknown as ResultData;
          sendToRenderer("pipeline:result", resultData);
          onResult?.(resultData);
          break;
        }
        case "error": {
          const errorData: ErrorData = {
            message: msg.message ?? "Unknown pipeline error",
            stage: msg.stage,
          };
          sendToRenderer("pipeline:error", errorData);
          onError?.(errorData);
          break;
        }
      }
    }
  });

  // Capture stderr for logging
  let stderrBuffer = "";
  childProcess.stderr?.on("data", (chunk: Buffer) => {
    stderrBuffer += chunk.toString("utf-8");
    const lines = stderrBuffer.split("\n");
    stderrBuffer = lines.pop() ?? "";
    for (const line of lines) {
      const trimmed = line.trim();
      if (trimmed) {
        logger.debug(`Pipeline stderr: ${trimmed}`, "PipelineRunner");
      }
    }
  });

  childProcess.on("error", (err) => {
    running = false;
    childProcess = null;
    const errorData: ErrorData = {
      message: `Failed to start pipeline process: ${err.message}`,
    };
    logger.error(errorData.message, "PipelineRunner");
    sendToRenderer("pipeline:error", errorData);
    onError?.(errorData);
  });

  childProcess.on("close", (code) => {
    running = false;
    childProcess = null;

    // Flush remaining stdout buffer
    if (stdoutBuffer.trim()) {
      try {
        const msg = JSON.parse(stdoutBuffer.trim()) as PipelineMessage;
        if (msg.type === "result" && msg.data) {
          const resultData = msg.data as unknown as ResultData;
          sendToRenderer("pipeline:result", resultData);
          onResult?.(resultData);
        }
      } catch {
        logger.debug(`Pipeline final stdout: ${stdoutBuffer.trim()}`, "PipelineRunner");
      }
    }

    if (code !== 0 && code !== null) {
      const errorData: ErrorData = {
        message: `Pipeline process exited with code ${code}`,
      };
      logger.warn(errorData.message, "PipelineRunner");
      sendToRenderer("pipeline:error", errorData);
      onError?.(errorData);
    }

    logger.info(`Pipeline process exited with code ${code}`, "PipelineRunner");
  });
}

export function stopPipeline(): void {
  if (!childProcess || !running) {
    logger.info("No running pipeline to stop", "PipelineRunner");
    return;
  }

  logger.info("Stopping pipeline process...", "PipelineRunner");

  // Try graceful termination first (SIGTERM), then force after timeout
  childProcess.kill("SIGTERM");

  const forceKillTimer = setTimeout(() => {
    if (childProcess && !childProcess.killed) {
      logger.warn("Force-killing pipeline process (SIGKILL)", "PipelineRunner");
      childProcess.kill("SIGKILL");
    }
  }, 5000);

  childProcess.once("close", () => {
    clearTimeout(forceKillTimer);
  });
}

export function isPipelineRunning(): boolean {
  return running;
}
