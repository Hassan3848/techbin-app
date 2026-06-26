import React, { createContext, useContext, useEffect, useMemo, useState, ReactNode } from "react";
import type { User as SupabaseUser } from "@supabase/supabase-js";
import { supabase, type ProfileRow } from "../../shared/supabase";

export type UserRole = "Admin" | "Viewer";

export interface User {
  uid: string;
  email: string;
  role: UserRole;
  orgId: string;
  superAdmin: boolean;
}

interface AuthContextType {
  user: User | null;
  login: (email: string, password: string) => Promise<boolean>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
  isAuthenticated: boolean;
  loading: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

function mapProfileToUser(profile: ProfileRow): User {
  return {
    uid: profile.id,
    email: profile.email,
    role: profile.role === "Admin" ? "Admin" : "Viewer",
    orgId: profile.org_id || "unknown",
    superAdmin: profile.super_admin === true,
  };
}

async function bootstrapRootAdminIfAllowed(authUser: SupabaseUser) {
  const email = (authUser.email || "").trim().toLowerCase();
  if (email !== "admin@techbin.com") return;

  try {
    await supabase.functions.invoke("bootstrap-admin-profile", { body: {} });
  } catch (err) {
    console.info("Root admin bootstrap skipped:", err);
  }
}

async function loadProfile(authUser: SupabaseUser): Promise<User | null> {
  await bootstrapRootAdminIfAllowed(authUser);

  const { data, error } = await supabase
    .from("profiles")
    .select("*")
    .eq("id", authUser.id)
    .eq("disabled", false)
    .single();

  if (error || !data) {
    console.error("Profile load failed:", error);
    return null;
  }

  return mapProfileToUser(data as ProfileRow);
}

export const AuthProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const refreshUser = async () => {
    setLoading(true);
    try {
      const { data } = await supabase.auth.getUser();
      setUser(data.user ? await loadProfile(data.user) : null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let active = true;

    supabase.auth.getUser().then(async ({ data }) => {
      if (!active) return;
      setUser(data.user ? await loadProfile(data.user) : null);
      setLoading(false);
    });

    const { data: listener } = supabase.auth.onAuthStateChange(async (_event, session) => {
      setLoading(true);
      try {
        setUser(session?.user ? await loadProfile(session.user) : null);
      } finally {
        setLoading(false);
      }
    });

    return () => {
      active = false;
      listener.subscription.unsubscribe();
    };
  }, []);

  const login = async (email: string, password: string): Promise<boolean> => {
    setLoading(true);
    try {
      const { data, error } = await supabase.auth.signInWithPassword({
        email: email.trim().toLowerCase(),
        password,
      });

      if (error || !data.user) throw error ?? new Error("Login failed.");
      const appUser = await loadProfile(data.user);
      if (!appUser) throw new Error("No active profile exists for this account.");

      setUser(appUser);
      return true;
    } catch (err) {
      console.error("Login failed:", err);
      setUser(null);
      await supabase.auth.signOut();
      return false;
    } finally {
      setLoading(false);
    }
  };

  const logout = async () => {
    setLoading(true);
    try {
      await supabase.auth.signOut();
      setUser(null);
    } finally {
      setLoading(false);
    }
  };

  const value = useMemo<AuthContextType>(
    () => ({
      user,
      login,
      logout,
      refreshUser,
      isAuthenticated: !!user,
      loading,
    }),
    [user, loading]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider");
  return context;
};
