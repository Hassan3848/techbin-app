function parseBooleanFlag(value: string | undefined, fallback = false) {
  if (value == null) return fallback;
  const normalized = value.trim().toLowerCase();
  return normalized === "1" || normalized === "true" || normalized === "yes" || normalized === "on";
}

export const featureFlags = {
  piDevices: parseBooleanFlag(import.meta.env.VITE_ENABLE_PI_DEVICES, false),
};
