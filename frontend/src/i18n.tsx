import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export type Language = "zh" | "en";

type LanguageContextValue = {
  language: Language;
  locale: string;
  choose: (zh: string, en: string) => string;
  toggleLanguage: () => void;
};

const STORAGE_KEY = "pssa-language";
const LanguageContext = createContext<LanguageContextValue | null>(null);

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [language, setLanguage] = useState<Language>(() =>
    window.localStorage.getItem(STORAGE_KEY) === "en" ? "en" : "zh",
  );

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, language);
    document.documentElement.lang = language === "zh" ? "zh-CN" : "en";
  }, [language]);

  const value = useMemo<LanguageContextValue>(
    () => ({
      language,
      locale: language === "zh" ? "zh-SG" : "en-SG",
      choose: (zh, en) => selectText(language, zh, en),
      toggleLanguage: () => setLanguage((current) => (current === "zh" ? "en" : "zh")),
    }),
    [language],
  );

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLanguage() {
  const context = useContext(LanguageContext);
  if (!context) throw new Error("useLanguage must be used inside LanguageProvider");
  return context;
}

export function selectText(language: Language, zh: string, en: string) {
  return language === "zh" ? zh : en;
}

const KNOWN_MESSAGES: Record<string, string> = {
  "用户名或密码错误。": "Incorrect username or password.",
  "用户名已存在。": "The username is already in use.",
  "该用户名为管理员保留。": "This username is reserved for the administrator demo.",
  "密码至少需要 10 个字符。": "The password must contain at least 10 characters.",
  "请求过于频繁，请稍后重试。": "Too many requests. Please try again later.",
  "天气暂时不可用。": "Weather is temporarily unavailable.",
};

export function localizeKnownMessage(message: string, language: Language) {
  if (language === "zh") return message;
  return KNOWN_MESSAGES[message] ?? message;
}
