import React, { createContext, useContext, useEffect, useMemo, useState, ReactNode } from "react";
import { supabase } from "../../shared/supabase";
import { useAuth } from "./AuthProvider";

export type ThemeMode = "light" | "dark";

export type SettingsState = {
  refreshRate: string;
  sessionTimeout: string;
  theme: ThemeMode;
  notifications: boolean;
};

export const DEFAULT_SETTINGS: SettingsState = {
  refreshRate: "10",
  sessionTimeout: "30",
  theme: "light",
  notifications: true,
};

const REFRESH_OPTIONS = new Set(["5", "10", "30", "60"]);
const SESSION_OPTIONS = new Set(["15", "30", "60", "120"]);

interface SettingsContextType {
  settings: SettingsState;
  loading: boolean;
  saveSettings: (next: SettingsState) => Promise<void>;
}

const SettingsContext = createContext<SettingsContextType | undefined>(undefined);

function safeSelect(value: unknown, allowed: Set<string>, fallback: string): string {
  const parsed = String(value ?? "");
  return allowed.has(parsed) ? parsed : fallback;
}

function normalizeSettings(data: Record<string, unknown> | null | undefined): SettingsState {
  if (!data) return DEFAULT_SETTINGS;
  return {
    refreshRate: safeSelect(data.refresh_rate, REFRESH_OPTIONS, DEFAULT_SETTINGS.refreshRate),
    sessionTimeout: safeSelect(data.session_timeout, SESSION_OPTIONS, DEFAULT_SETTINGS.sessionTimeout),
    theme: data.theme === "dark" ? "dark" : "light",
    notifications: data.notifications !== false,
  };
}

export const SettingsProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const { user, logout } = useAuth();
  const [settings, setSettings] = useState<SettingsState>(DEFAULT_SETTINGS);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!user?.uid) {
      setSettings(DEFAULT_SETTINGS);
      setLoading(false);
      return;
    }

    let active = true;
    setLoading(true);

    const load = async () => {
      const { data, error } = await supabase
        .from("user_settings")
        .select("*")
        .eq("user_id", user.uid)
        .maybeSingle();

      if (!active) return;
      if (error) console.error("settings load error:", error);
      setSettings(normalizeSettings(data as Record<string, unknown> | null));
      setLoading(false);
    };

    load();

    const channel = supabase
      .channel(`settings:${user.uid}`)
      .on(
        "postgres_changes",
        { event: "*", schema: "public", table: "user_settings", filter: `user_id=eq.${user.uid}` },
        (payload) => {
          setSettings(normalizeSettings(payload.new as Record<string, unknown>));
        }
      )
      .subscribe();

    return () => {
      active = false;
      supabase.removeChannel(channel);
    };
  }, [user?.uid]);

  useEffect(() => {
    const root = document.documentElement;
    const dark = settings.theme === "dark";
    root.classList.toggle("dark", dark);
    root.style.colorScheme = dark ? "dark" : "light";
  }, [settings.theme]);

  useEffect(() => {
    if (!user?.uid) return;

    const timeoutMs = Number(settings.sessionTimeout) * 60 * 1000;
    if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) return;

    let timer = window.setTimeout(() => {
      logout();
    }, timeoutMs);

    const resetTimer = () => {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => {
        logout();
      }, timeoutMs);
    };

    const events: Array<keyof WindowEventMap> = ["click", "keydown", "mousemove", "scroll", "touchstart"];
    events.forEach((eventName) => window.addEventListener(eventName, resetTimer, { passive: true }));

    return () => {
      window.clearTimeout(timer);
      events.forEach((eventName) => window.removeEventListener(eventName, resetTimer));
    };
  }, [user?.uid, settings.sessionTimeout, logout]);

  const saveSettings = async (next: SettingsState) => {
    if (!user?.uid) throw new Error("You must be logged in.");

    const { error } = await supabase.from("user_settings").upsert({
      user_id: user.uid,
      org_id: user.orgId,
      refresh_rate: next.refreshRate,
      session_timeout: next.sessionTimeout,
      theme: next.theme,
      notifications: next.notifications,
      updated_at: new Date().toISOString(),
      updated_by: user.email,
    });

    if (error) throw error;
    setSettings(next);
  };

  const value = useMemo<SettingsContextType>(
    () => ({
      settings,
      loading,
      saveSettings,
    }),
    [settings, loading]
  );

  return <SettingsContext.Provider value={value}>{children}</SettingsContext.Provider>;
};

export const useSettings = () => {
  const context = useContext(SettingsContext);
  if (!context) throw new Error("useSettings must be used within SettingsProvider");
  return context;
};
