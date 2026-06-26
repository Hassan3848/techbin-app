import { corsHeaders, jsonResponse } from "../_shared/cors.ts";
import { requireAdmin, requireCallerProfile } from "../_shared/admin.ts";

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
  if (req.method !== "POST") return jsonResponse({ error: "Method not allowed." }, 405);

  try {
    const { client, profile } = await requireCallerProfile(req);
    requireAdmin(profile);

    const body = await req.json();
    const uid = String(body.uid ?? "").trim();
    if (!uid) return jsonResponse({ error: "uid is required." }, 400);
    if (uid === profile.id) return jsonResponse({ error: "You cannot delete your own account." }, 400);

    const { data: target, error: targetError } = await client
      .from("profiles")
      .select("id,email,role,org_id,super_admin")
      .eq("id", uid)
      .single();

    if (targetError || !target) return jsonResponse({ error: "Target user not found." }, 404);
    if (!profile.super_admin && target.org_id !== profile.org_id) {
      return jsonResponse({ error: "You can only delete users in your organization." }, 403);
    }
    if (target.super_admin) return jsonResponse({ error: "Super admin cannot be deleted here." }, 403);
    if (!profile.super_admin && target.role !== "Viewer") {
      return jsonResponse({ error: "Org admins can delete viewer users only." }, 403);
    }

    const { error: deleteAuthError } = await client.auth.admin.deleteUser(uid);
    if (deleteAuthError) throw deleteAuthError;

    await client.from("profiles").delete().eq("id", uid);
    return jsonResponse({ ok: true });
  } catch (error) {
    return jsonResponse({ error: error instanceof Error ? error.message : "Delete user failed." }, 400);
  }
});
