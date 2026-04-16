import { useState, useEffect } from 'react'

export function useSettings() {
  const [settings, setSettings] = useState<{
    geminiApiKey: string
    entrezEmail: string
    outputDirectory: string
    theme: 'light' | 'dark' | 'system'
    onboardingComplete: boolean
    parallelAnalysis: boolean
  } | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    window.api.settings.get().then((s) => {
      setSettings(s)
      setLoading(false)
    })
  }, [])

  const updateSetting = async (key: string, value: unknown) => {
    await window.api.settings.set(key, value)
    const updated = await window.api.settings.get()
    setSettings(updated)
  }

  return { settings, loading, updateSetting }
}
