/**
 * Logger Service — structured file-based logging with rotation.
 * Logs to the Electron app data directory.
 */

import { app } from "electron";
import fs from "node:fs";
import path from "node:path";

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

type LogLevel = "debug" | "info" | "warn" | "error";

const LOG_LEVELS: Record<LogLevel, number> = {
  debug: 0,
  info: 1,
  warn: 2,
  error: 3,
};

const MAX_FILE_SIZE = 5 * 1024 * 1024; // 5 MB
const MAX_FILES = 5;
const LOG_FILE_NAME = "disease2gene.log";

// ---------------------------------------------------------------------------
// Logger implementation
// ---------------------------------------------------------------------------

class Logger {
  private logDir: string;
  private minLevel: LogLevel = "info";

  constructor() {
    // Fallback for when app is not ready yet
    try {
      this.logDir = path.join(app.getPath("userData"), "logs");
    } catch {
      this.logDir = path.join(
        process.env.HOME ?? process.env.USERPROFILE ?? "/tmp",
        ".disease2gene",
        "logs",
      );
    }
    this.ensureLogDir();
  }

  setLevel(level: LogLevel): void {
    this.minLevel = level;
  }

  debug(message: string, module?: string): void {
    this.log("debug", message, module);
  }

  info(message: string, module?: string): void {
    this.log("info", message, module);
  }

  warn(message: string, module?: string): void {
    this.log("warn", message, module);
  }

  error(message: string, module?: string): void {
    this.log("error", message, module);
  }

  /**
   * Get recent log entries for display in the UI.
   */
  getRecentLogs(count = 100): string[] {
    const logPath = this.currentLogPath();
    if (!fs.existsSync(logPath)) return [];

    try {
      const content = fs.readFileSync(logPath, "utf-8");
      const lines = content.split("\n").filter((l) => l.trim().length > 0);
      return lines.slice(-count);
    } catch {
      return [];
    }
  }

  /**
   * Get the log directory path.
   */
  getLogDir(): string {
    return this.logDir;
  }

  // -------------------------------------------------------------------------
  // Internal
  // -------------------------------------------------------------------------

  private log(level: LogLevel, message: string, module?: string): void {
    if (LOG_LEVELS[level] < LOG_LEVELS[this.minLevel]) return;

    const timestamp = new Date().toISOString();
    const moduleTag = module ? ` [${module}]` : "";
    const line = `[${timestamp}] [${level.toUpperCase()}]${moduleTag} ${message}`;

    // Always write to console
    switch (level) {
      case "error":
        console.error(line);
        break;
      case "warn":
        console.warn(line);
        break;
      default:
        console.log(line);
    }

    // Write to file
    this.writeToFile(line);
  }

  private writeToFile(line: string): void {
    try {
      this.ensureLogDir();
      const logPath = this.currentLogPath();

      // Check if rotation is needed
      if (fs.existsSync(logPath)) {
        const stat = fs.statSync(logPath);
        if (stat.size >= MAX_FILE_SIZE) {
          this.rotate();
        }
      }

      fs.appendFileSync(logPath, line + "\n", "utf-8");
    } catch {
      // If we can't write to file, we've already written to console
    }
  }

  private rotate(): void {
    try {
      // Delete oldest log if at max
      const oldest = this.logFilePath(MAX_FILES - 1);
      if (fs.existsSync(oldest)) {
        fs.unlinkSync(oldest);
      }

      // Shift existing logs
      for (let i = MAX_FILES - 2; i >= 1; i--) {
        const from = this.logFilePath(i);
        const to = this.logFilePath(i + 1);
        if (fs.existsSync(from)) {
          fs.renameSync(from, to);
        }
      }

      // Rename current to .1
      const current = this.currentLogPath();
      if (fs.existsSync(current)) {
        fs.renameSync(current, this.logFilePath(1));
      }
    } catch {
      // Rotation failure is non-critical
    }
  }

  private currentLogPath(): string {
    return path.join(this.logDir, LOG_FILE_NAME);
  }

  private logFilePath(index: number): string {
    return path.join(this.logDir, `disease2gene.${index}.log`);
  }

  private ensureLogDir(): void {
    try {
      if (!fs.existsSync(this.logDir)) {
        fs.mkdirSync(this.logDir, { recursive: true });
      }
    } catch {
      // Best-effort directory creation
    }
  }
}

// ---------------------------------------------------------------------------
// Singleton export
// ---------------------------------------------------------------------------

export const logger = new Logger();
