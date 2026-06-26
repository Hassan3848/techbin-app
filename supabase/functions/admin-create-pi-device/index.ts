import { corsHeaders, jsonResponse } from "../_shared/cors.ts";
import { requireCallerProfile, requireSuperAdmin } from "../_shared/admin.ts";

async function sha256Hex(value: string) {
  const bytes = new TextEncoder().encode(value);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

function generateToken() {
  return `tb_pi_${crypto.randomUUID().replace(/-/g, "")}`;
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
  if (req.method !== "POST") return jsonResponse({ error: "Method not allowed." }, 405);

  try {
    const { client, profile } = await requireCallerProfile(req);
    requireSuperAdmin(profile);

    const body = await req.json();
    const binId = String(body.binId ?? "").trim();
    const deviceName = String(body.deviceName ?? "").trim();

    if (!binId) return jsonResponse({ error: "binId is required." }, 400);
    if (!deviceName) return jsonResponse({ error: "deviceName is required." }, 400);

    const { data: bin, error: binError } = await client
      .from("bins")
      .select("id,org_id,bin_code")
      .eq("id", binId)
      .single();

    if (binError || !bin) return jsonResponse({ error: "Bin not found." }, 404);

    const token = generateToken();
    const tokenHash = await sha256Hex(token);

    const { data: createdDevice, error: createError } = await client
      .from("pi_devices")
      .insert({
        bin_id: bin.id,
        org_id: bin.org_id,
        bin_code: bin.bin_code,
        device_name: deviceName,
        token_hash: tokenHash,
        active: true,
      })
      .select("id,device_name,bin_code,org_id")
      .single();

    if (createError || !createdDevice) throw createError ?? new Error("Pi device creation failed.");

    return jsonResponse({
      id: createdDevice.id,
      deviceName: createdDevice.device_name,
      binCode: createdDevice.bin_code,
      orgId: createdDevice.org_id,
      token,
    });
  } catch (error) {
    return jsonResponse({ error: error instanceof Error ? error.message : "Create Pi device failed." }, 400);
  }
});
