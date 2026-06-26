import { createClient } from "@supabase/supabase-js";

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

if (!supabaseUrl || !supabaseAnonKey) {
  throw new Error("Missing Supabase environment variables. Set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY.");
}

export const supabase = createClient(supabaseUrl, supabaseAnonKey, {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
    detectSessionInUrl: true,
  },
  realtime: {
    params: {
      eventsPerSecond: 10,
    },
  },
});

export type AppRole = "Admin" | "Viewer";

export type ProfileRow = {
  id: string;
  email: string;
  display_name: string | null;
  role: AppRole;
  org_id: string;
  super_admin: boolean;
  disabled: boolean;
  created_at: string | null;
  created_by: string | null;
  updated_at: string | null;
  updated_by: string | null;
};

export type BinRow = {
  id: string;
  org_id: string;
  bin_code: string;
  location: string | null;
  status: "Active" | "Maintenance" | "Inactive";
  capacity_liters: number | null;
  created_at: string | null;
  created_by: string | null;
  updated_at: string | null;
  updated_by: string | null;
};

export type PiDeviceRow = {
  id: string;
  bin_id: string;
  org_id: string;
  bin_code: string;
  device_name: string;
  token_hash: string;
  active: boolean;
  last_seen: string | null;
  created_at: string | null;
};
