import { corsHeaders, jsonResponse } from "../_shared/cors.ts";
import { requireCallerProfile, requireSuperAdmin } from "../_shared/admin.ts";

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
  if (req.method !== "POST") return jsonResponse({ error: "Method not allowed." }, 405);

  try {
    const { client, profile } = await requireCallerProfile(req);
    requireSuperAdmin(profile);

    const body = await req.json();
    const deviceId = String(body.deviceId ?? "").trim();
    const active = body.active === true;

    if (!deviceId) return jsonResponse({ error: "deviceId is required." }, 400);

    const { error } = await client
      .from("pi_devices")
      .update({ active })
      .eq("id", deviceId);

    if (error) throw error;
    return jsonResponse({ ok: true });
  } catch (error) {
    return jsonResponse({ error: error instanceof Error ? error.message : "Update Pi device failed." }, 400);
  }
});
