import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "./en.json";
import hi from "./hi.json";
import mr from "./mr.json";

// HI and MR are machine-drafted; every string is flagged `needs_native_review` and the picker says so.
export const LANGS = [
  { code: "en", label: "English", review: false },
  { code: "hi", label: "हिन्दी", review: Boolean((hi as any)._meta.needs_native_review) },
  { code: "mr", label: "मराठी", review: Boolean((mr as any)._meta.needs_native_review) },
] as const;

const KEY = "phl.lang";
function stored(): string {
  try {
    return localStorage.getItem(KEY) ?? "en";
  } catch {
    return "en";
  }
}

void i18n.use(initReactI18next).init({
  resources: { en: { translation: en }, hi: { translation: hi }, mr: { translation: mr } },
  lng: stored(),
  fallbackLng: "en",
  interpolation: { escapeValue: false },
});

export function setLanguage(code: string) {
  void i18n.changeLanguage(code);
  try {
    localStorage.setItem(KEY, code);
  } catch {
    /* ignore */
  }
  document.documentElement.lang = code;
}

export default i18n;
