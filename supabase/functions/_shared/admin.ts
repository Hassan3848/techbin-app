import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

export type Profile = {
  id: string;
  email: string;
  role: "Admin" | "Viewer";
  org_id: string;
  super_admin: boolean;
  disabled: boolean;
};

export function adminClient() {
  return createClient(
    Deno.env.get("SUPABASE_URL") ?? "",
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "",
    { auth: { persistSession: false } }
  );
}

export async function requireCallerProfile(req: Request): Promise<{ client: ReturnType<typeof adminClient>; profile: Profile }> {
  const client = adminClient();
  const authHeader = req.headers.get("Authorization");
  if (!authHeader) throw new Error("Missing Authorization header.");

  const token = authHeader.replace("Bearer ", "");
  const { data: userData, error: userError } = await client.auth.getUser(token);
  if (userError || !userData.user) throw new Error("Invalid session.");

  const { data: profile, error: profileError } = await client
    .from("profiles")
    .select("id,email,role,org_id,super_admin,disabled")
    .eq("id", userData.user.id)
    .single();

  if (profileError || !profile || profile.disabled) throw new Error("Profile not found or disabled.");
  return { client, profile: profile as Profile };
}

export function requireAdmin(profile: Profile) {
  if (profile.role !== "Admin") throw new Error("Admin permission required.");
}

export function requireSuperAdmin(profile: Profile) {
  if (!profile.super_admin) throw new Error("Super Admin permission required.");
}

export function normalizeOrgId(value: unknown, fallback = "techbin") {
  const orgId = String(value ?? "").trim().toLowerCase();
  return orgId || fallback;
}
