import Store from 'electron-store'

interface UsageSchema {
  geminiDailyUsage: { date: string; used: number }
}

const GEMINI_FREE_TIER_DAILY_LIMIT = 1000

const usageStore = new Store<UsageSchema>({
  name: 'usage',
  defaults: { geminiDailyUsage: { date: '', used: 0 } }
})

function todayDate(): string {
  return new Date().toISOString().slice(0, 10) // YYYY-MM-DD
}

export function getGeminiDailyUsage(): { used: number; limit: number; date: string } {
  const stored = usageStore.get('geminiDailyUsage')
  const today = todayDate()
  if (stored.date !== today) {
    return { used: 0, limit: GEMINI_FREE_TIER_DAILY_LIMIT, date: today }
  }
  return { used: stored.used, limit: GEMINI_FREE_TIER_DAILY_LIMIT, date: stored.date }
}

export function addGeminiApiCalls(count: number): void {
  if (count <= 0) return
  const today = todayDate()
  const stored = usageStore.get('geminiDailyUsage')
  if (stored.date !== today) {
    usageStore.set('geminiDailyUsage', { date: today, used: count })
  } else {
    usageStore.set('geminiDailyUsage', { date: today, used: stored.used + count })
  }
}
