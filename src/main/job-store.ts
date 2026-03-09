import Database from 'better-sqlite3'
import { app } from 'electron'
import { join } from 'path'

export interface Job {
  id: string
  query: string
  columns: string // JSON
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'
  created_at: string
  completed_at: string | null
  result_path: string | null
  stats: string | null // JSON
  error: string | null
}

let db: Database.Database

function getDb(): Database.Database {
  if (!db) {
    const dbPath = join(app.getPath('userData'), 'jobs.db')
    db = new Database(dbPath)
    db.pragma('journal_mode = WAL')
    db.exec(`
      CREATE TABLE IF NOT EXISTS jobs (
        id TEXT PRIMARY KEY,
        query TEXT NOT NULL,
        columns TEXT NOT NULL DEFAULT '{}',
        status TEXT NOT NULL DEFAULT 'queued',
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        completed_at TEXT,
        result_path TEXT,
        stats TEXT,
        error TEXT
      )
    `)
  }
  return db
}

export function createJob(id: string, query: string, columns: string): Job {
  const d = getDb()
  const stmt = d.prepare('INSERT INTO jobs (id, query, columns) VALUES (?, ?, ?)')
  stmt.run(id, query, columns)
  return getJob(id)!
}

export function getJob(id: string): Job | null {
  const d = getDb()
  return d.prepare('SELECT * FROM jobs WHERE id = ?').get(id) as Job | null
}

export function updateJob(id: string, updates: Partial<Omit<Job, 'id'>>): void {
  const d = getDb()
  const fields = Object.entries(updates)
    .map(([key]) => `${key} = ?`)
    .join(', ')
  const values = Object.values(updates)
  d.prepare(`UPDATE jobs SET ${fields} WHERE id = ?`).run(...values, id)
}

export function listJobs(limit = 50): Job[] {
  const d = getDb()
  return d.prepare('SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?').all(limit) as Job[]
}

export function deleteJob(id: string): void {
  const d = getDb()
  d.prepare('DELETE FROM jobs WHERE id = ?').run(id)
}
