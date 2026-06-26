import { jsonResponse, corsHeaders } from "../_shared/cors.ts";
import { adminClient, normalizeOrgId } from "../_shared/admin.ts";

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
  if (req.method !== "POST") return jsonResponse({ error: "Method not allowed." }, 405);

  try {
    const client = adminClient();
    const authHeader = req.headers.get("Authorization");
    if (!authHeader) return jsonResponse({ error: "Missing Authorization header." }, 401);

    const token = authHeader.replace("Bearer ", "");
    const { data, error } = await client.auth.getUser(token);
    if (error || !data.user?.email) return jsonResponse({ error: "Invalid session." }, 401);

    const rootEmail = (Deno.env.get("TECHBIN_ROOT_ADMIN_EMAIL") || "admin@techbin.com").toLowerCase();
    const email = data.user.email.toLowerCase();
    if (email !== rootEmail) return jsonResponse({ skipped: true });

    const { error: upsertError } = await client.from("profiles").upsert({
      id: data.user.id,
      email,
      role: "Admin",
      org_id: normalizeOrgId(Deno.env.get("TECHBIN_ROOT_ORG_ID"), "techbin"),
      super_admin: true,
      disabled: false,
      updated_at: new Date().toISOString(),
      updated_by: "bootstrap-admin-profile",
    });

    if (upsertError) throw upsertError;
    return jsonResponse({ ok: true });
  } catch (error) {
    return jsonResponse({ error: error instanceof Error ? error.message : "Bootstrap failed." }, 400);
  }
});
