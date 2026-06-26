import React, { useEffect, useMemo, useState } from "react";
import { Bell, CheckCircle2, Clock, Moon, RefreshCw, Save, Shield, Sun } from "lucide-react";
import { useAuth } from "../../app/providers/AuthProvider";
import { DEFAULT_SETTINGS, SettingsState, ThemeMode, useSettings } from "../../app/providers/SettingsProvider";

const refreshOptions = [
  { value: "5", label: "5 sec" },
  { value: "10", label: "10 sec" },
  { value: "30", label: "30 sec" },
  { value: "60", label: "60 sec" },
];

const sessionOptions = [
  { value: "15", label: "15 min" },
  { value: "30", label: "30 min" },
  { value: "60", label: "60 min" },
  { value: "120", label: "120 min" },
];

function Toggle({
  checked,
  disabled,
  onChange,
}: {
  checked: boolean;
  disabled?: boolean;
  onChange: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onChange}
      disabled={disabled}
      aria-pressed={checked}
      className={`relative inline-flex h-7 w-12 shrink-0 items-center rounded-full transition-colors disabled:opacity-50 ${
        checked ? "bg-emerald-600" : "bg-gray-300"
      }`}
    >
      <span
        className={`inline-block h-5 w-5 rounded-full bg-white shadow-sm transition-transform ${
          checked ? "translate-x-6" : "translate-x-1"
        }`}
      />
    </button>
  );
}

function OptionGrid({
  value,
  options,
  disabled,
  onChange,
}: {
  value: string;
  options: Array<{ value: string; label: string }>;
  disabled?: boolean;
  onChange: (value: string) => void;
}) {
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          disabled={disabled}
          onClick={() => onChange(option.value)}
          className={`min-h-10 rounded-lg border px-3 text-sm transition-colors disabled:opacity-50 ${
            value === option.value
              ? "border-emerald-600 bg-emerald-50 text-emerald-700"
              : "border-gray-200 bg-white text-gray-700 hover:bg-gray-50"
          }`}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

export const SettingsPage: React.FC = () => {
  const { user } = useAuth();
  const { settings, loading, saveSettings } = useSettings();

  const [refreshRate, setRefreshRate] = useState(DEFAULT_SETTINGS.refreshRate);
  const [sessionTimeout, setSessionTimeout] = useState(DEFAULT_SETTINGS.sessionTimeout);
  const [theme, setTheme] = useState<ThemeMode>(DEFAULT_SETTINGS.theme);
  const [notifications, setNotifications] = useState(DEFAULT_SETTINGS.notifications);
  const [initialSettings, setInitialSettings] = useState<SettingsState>(DEFAULT_SETTINGS);
  const [saving, setSaving] = useState(false);
  const [statusText, setStatusText] = useState("");
  const [statusError, setStatusError] = useState(false);

  const currentSettings: SettingsState = useMemo(
    () => ({
      refreshRate,
      sessionTimeout,
      theme,
      notifications,
    }),
    [refreshRate, sessionTimeout, theme, notifications]
  );

  const hasChanges = useMemo(() => {
    return JSON.stringify(currentSettings) !== JSON.stringify(initialSettings);
  }, [currentSettings, initialSettings]);

  useEffect(() => {
    setRefreshRate(settings.refreshRate);
    setSessionTimeout(settings.sessionTimeout);
    setTheme(settings.theme);
    setNotifications(settings.notifications);
    setInitialSettings(settings);
  }, [settings]);

  const toggleNotifications = async () => {
    setStatusText("");
    setStatusError(false);

    if (notifications) {
      setNotifications(false);
      return;
    }

    if (!("Notification" in window)) {
      setStatusText("Browser notifications are not available.");
      setStatusError(true);
      return;
    }

    if (Notification.permission === "denied") {
      setStatusText("Browser notifications are blocked.");
      setStatusError(true);
      return;
    }

    if (Notification.permission === "default") {
      const permission = await Notification.requestPermission();
      if (permission !== "granted") {
        setStatusText("Notification permission was not granted.");
        setStatusError(true);
        return;
      }
    }

    setNotifications(true);
  };

  const handleSaveSettings = async () => {
    if (!user?.uid) return;

    setSaving(true);
    setStatusText("");
    setStatusError(false);

    try {
      await saveSettings(currentSettings);
      setInitialSettings(currentSettings);
      setStatusText("Settings saved.");
      setStatusError(false);
    } catch (error) {
      console.error("Failed to save settings:", error);
      setStatusText("Settings could not be saved.");
      setStatusError(true);
    } finally {
      setSaving(false);
    }
  };

  const disabled = loading || saving;
  const notificationStatus =
    "Notification" in window ? Notification.permission : "unavailable";

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 pb-24 lg:pb-6">
      <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-2xl text-gray-900">Settings</h1>
          <p className="mt-1 text-sm text-gray-600">User preferences for this dashboard session.</p>
        </div>

        <div className="rounded-lg border border-gray-200 bg-white px-4 py-3 text-sm text-gray-700 shadow-sm">
          <div className="font-medium text-gray-900">{user?.email || "-"}</div>
          <div className="text-xs text-emerald-700">
            {user?.superAdmin ? "Super Admin" : user?.role || "-"} · {user?.orgId || "-"}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-[1fr_360px]">
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
          <section className="rounded-xl border border-gray-100 bg-white p-5 shadow-sm">
            <div className="mb-4 flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-emerald-50">
                <RefreshCw className="h-5 w-5 text-emerald-600" />
              </div>
              <div>
                <h2 className="text-lg text-gray-900">Live Refresh</h2>
                <p className="text-xs text-gray-500">Fallback interval for live views.</p>
              </div>
            </div>

            <OptionGrid
              value={refreshRate}
              options={refreshOptions}
              disabled={disabled}
              onChange={setRefreshRate}
            />
          </section>

          <section className="rounded-xl border border-gray-100 bg-white p-5 shadow-sm">
            <div className="mb-4 flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-50">
                <Clock className="h-5 w-5 text-blue-600" />
              </div>
              <div>
                <h2 className="text-lg text-gray-900">Session Timeout</h2>
                <p className="text-xs text-gray-500">Inactive users are signed out.</p>
              </div>
            </div>

            <OptionGrid
              value={sessionTimeout}
              options={sessionOptions}
              disabled={disabled}
              onChange={setSessionTimeout}
            />
          </section>

          <section className="rounded-xl border border-gray-100 bg-white p-5 shadow-sm">
            <div className="mb-4 flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-amber-50">
                {theme === "dark" ? (
                  <Moon className="h-5 w-5 text-amber-600" />
                ) : (
                  <Sun className="h-5 w-5 text-amber-600" />
                )}
              </div>
              <div>
                <h2 className="text-lg text-gray-900">Appearance</h2>
                <p className="text-xs text-gray-500">Saved per user.</p>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => setTheme("light")}
                disabled={disabled}
                className={`flex min-h-11 items-center justify-center gap-2 rounded-lg border px-3 text-sm transition-colors disabled:opacity-50 ${
                  theme === "light"
                    ? "border-emerald-600 bg-emerald-50 text-emerald-700"
                    : "border-gray-200 bg-white text-gray-700 hover:bg-gray-50"
                }`}
              >
                <Sun className="h-4 w-4" />
                Light
              </button>
              <button
                type="button"
                onClick={() => setTheme("dark")}
                disabled={disabled}
                className={`flex min-h-11 items-center justify-center gap-2 rounded-lg border px-3 text-sm transition-colors disabled:opacity-50 ${
                  theme === "dark"
                    ? "border-emerald-600 bg-emerald-50 text-emerald-700"
                    : "border-gray-200 bg-white text-gray-700 hover:bg-gray-50"
                }`}
              >
                <Moon className="h-4 w-4" />
                Dark
              </button>
            </div>
          </section>

          <section className="rounded-xl border border-gray-100 bg-white p-5 shadow-sm">
            <div className="flex items-start justify-between gap-4">
              <div className="flex items-start gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-purple-50">
                  <Bell className="h-5 w-5 text-purple-600" />
                </div>
                <div>
                  <h2 className="text-lg text-gray-900">Notifications</h2>
                  <p className="mt-1 text-xs text-gray-500">Permission: {notificationStatus}</p>
                </div>
              </div>
              <Toggle checked={notifications} disabled={disabled} onChange={toggleNotifications} />
            </div>
          </section>
        </div>

        <aside className="space-y-5">
          <section className="rounded-xl border border-gray-100 bg-white p-5 shadow-sm">
            <h2 className="mb-4 flex items-center gap-2 text-lg text-gray-900">
              <Shield className="h-5 w-5 text-emerald-600" />
              Access
            </h2>

            <div className="space-y-3 text-sm">
              <div className="flex items-center justify-between gap-3 rounded-lg bg-gray-50 px-3 py-2">
                <span className="text-gray-600">Role</span>
                <span className="font-medium text-gray-900">{user?.superAdmin ? "Super Admin" : user?.role || "-"}</span>
              </div>
              <div className="flex items-center justify-between gap-3 rounded-lg bg-gray-50 px-3 py-2">
                <span className="text-gray-600">Organization</span>
                <span className="font-medium text-gray-900">{user?.orgId || "-"}</span>
              </div>
              <div className="flex items-center justify-between gap-3 rounded-lg bg-gray-50 px-3 py-2">
                <span className="text-gray-600">Connection</span>
                <span className="inline-flex items-center gap-1 font-medium text-emerald-700">
                  <CheckCircle2 className="h-4 w-4" />
                  Supabase
                </span>
              </div>
            </div>
          </section>

          <section className="rounded-xl border border-gray-200 bg-gray-50 p-5 text-sm text-gray-700">
            TechBin Dashboard is for internal organizational use. Account access is controlled by admins.
          </section>
        </aside>
      </div>

      <div className="fixed inset-x-0 bottom-0 z-20 border-t border-gray-200 bg-white/95 px-4 py-3 shadow-lg backdrop-blur lg:static lg:border lg:bg-white lg:shadow-sm">
        <div className="mx-auto flex max-w-6xl flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <p className={`min-h-5 text-sm ${statusError ? "text-red-600" : "text-emerald-700"}`}>
            {loading ? "Loading settings..." : statusText}
          </p>
          <button
            type="button"
            onClick={handleSaveSettings}
            disabled={disabled || !hasChanges || !user?.uid}
            className="inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-lg bg-emerald-600 px-5 text-white transition-colors hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto"
          >
            <Save className="h-4 w-4" />
            {saving ? "Saving..." : hasChanges ? "Save Settings" : "Saved"}
          </button>
        </div>
      </div>
    </div>
  );
};
