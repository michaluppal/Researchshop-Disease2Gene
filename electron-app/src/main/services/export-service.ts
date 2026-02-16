/**
 * Export Service — exports result data to CSV and JSON.
 * Uses Electron dialog for file path selection.
 */

import { dialog, BrowserWindow } from "electron";
import fs from "node:fs";
import { logger } from "./logger-service.js";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type ExportRecord = Record<string, unknown>;

// ---------------------------------------------------------------------------
// CSV Export
// ---------------------------------------------------------------------------

function escapeCSVField(value: unknown): string {
  const str = value === null || value === undefined ? "" : String(value);
  // If the field contains a comma, quote, or newline, wrap it in quotes
  if (str.includes(",") || str.includes('"') || str.includes("\n") || str.includes("\r")) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
}

function recordsToCSV(records: ExportRecord[]): string {
  if (records.length === 0) return "";

  // Collect all unique keys across records to form column headers
  const columnSet = new Set<string>();
  for (const record of records) {
    for (const key of Object.keys(record)) {
      columnSet.add(key);
    }
  }
  const columns = [...columnSet];

  const header = columns.map(escapeCSVField).join(",");
  const rows = records.map((record) =>
    columns.map((col) => escapeCSVField(record[col])).join(","),
  );

  return header + "\n" + rows.join("\n") + "\n";
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export async function exportCSV(
  records: ExportRecord[],
  filePath?: string,
): Promise<string> {
  const targetPath = filePath ?? (await promptSavePath("csv"));
  if (!targetPath) {
    throw new Error("Export cancelled by user");
  }

  const csvContent = recordsToCSV(records);
  // Write with UTF-8 BOM for Excel compatibility
  const bom = "\uFEFF";
  fs.writeFileSync(targetPath, bom + csvContent, "utf-8");

  logger.info(`Exported CSV to ${targetPath}`, "ExportService");
  return targetPath;
}

export async function exportJSON(
  records: ExportRecord[],
  filePath?: string,
): Promise<string> {
  const targetPath = filePath ?? (await promptSavePath("json"));
  if (!targetPath) {
    throw new Error("Export cancelled by user");
  }

  const jsonContent = JSON.stringify(records, null, 2);
  fs.writeFileSync(targetPath, jsonContent, "utf-8");

  logger.info(`Exported JSON to ${targetPath}`, "ExportService");
  return targetPath;
}

export async function exportResults(
  format: "csv" | "json",
  data: unknown,
): Promise<string> {
  const records = data as ExportRecord[];
  if (!Array.isArray(records)) {
    throw new Error("Export data must be an array of records");
  }

  if (format === "csv") {
    return exportCSV(records);
  }
  return exportJSON(records);
}

// ---------------------------------------------------------------------------
// File dialog
// ---------------------------------------------------------------------------

async function promptSavePath(
  format: "csv" | "json",
): Promise<string | undefined> {
  const filters =
    format === "csv"
      ? [{ name: "CSV Files", extensions: ["csv"] }]
      : [{ name: "JSON Files", extensions: ["json"] }];

  const defaultName = `disease2gene_results.${format}`;
  const focusedWindow = BrowserWindow.getFocusedWindow();

  const result = focusedWindow
    ? await dialog.showSaveDialog(focusedWindow, {
        defaultPath: defaultName,
        filters,
      })
    : await dialog.showSaveDialog({ defaultPath: defaultName, filters });

  if (result.canceled || !result.filePath) {
    return undefined;
  }
  return result.filePath;
}
