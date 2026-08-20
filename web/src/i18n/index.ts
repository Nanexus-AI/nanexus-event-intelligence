import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import en from './locales/en'
import zhCN from './locales/zh-CN'

export const languageStorageKey = 'nanexus.language'
export type Language = 'en' | 'zh-CN'
function initialLanguage(): Language {
  const stored = localStorage.getItem(languageStorageKey)
  if (stored === 'en' || stored === 'zh-CN') return stored
  return navigator.language.toLowerCase().startsWith('zh') ? 'zh-CN' : 'en'
}
void i18n.use(initReactI18next).init({ resources: { en: { translation: en }, 'zh-CN': { translation: zhCN } }, lng: initialLanguage(), fallbackLng: 'en', interpolation: { escapeValue: false } })
export async function setLanguage(language: Language) {
  localStorage.setItem(languageStorageKey, language)
  document.documentElement.lang = language
  await i18n.changeLanguage(language)
}
document.documentElement.lang = i18n.language
export default i18n
