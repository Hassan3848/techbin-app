import { corsHeaders, jsonResponse } from "../_shared/cors.ts";
import { normalizeOrgId, requireAdmin, requireCallerProfile } from "../_shared/admin.ts";

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
  if (req.method !== "POST") return jsonResponse({ error: "Method not allowed." }, 405);

  try {
    const { client, profile } = await requireCallerProfile(req);
    requireAdmin(profile);

    const body = await req.json();
    const email = String(body.email ?? "").trim().toLowerCase();
    const password = String(body.password ?? "");
    const requestedRole = body.role === "Admin" ? "Admin" : "Viewer";
    const role = profile.super_admin ? requestedRole : "Viewer";
    const orgId = profile.super_admin ? normalizeOrgId(body.orgId, profile.org_id) : profile.org_id;

    if (!email) return jsonResponse({ error: "Email is required." }, 400);
    if (password.length < 6) return jsonResponse({ error: "Password must be at least 6 characters." }, 400);

    const { data: created, error: createError } = await client.auth.admin.createUser({
      email,
      password,
      email_confirm: true,
      user_metadata: { role, org_id: orgId },
    });
    if (createError || !created.user) throw createError ?? new Error("User creation failed.");

    const { error: profileError } = await client.from("profiles").insert({
      id: created.user.id,
      email,
      role,
      org_id: orgId,
      super_admin: false,
      disabled: false,
      created_by: profile.email,
    });

    if (profileError) {
      await client.auth.admin.deleteUser(created.user.id);
      throw profileError;
    }

    return jsonResponse({ ok: true, id: created.user.id });
  } catch (error) {
    return jsonResponse({ error: error instanceof Error ? error.message : "Create user failed." }, 400);
  }
});
