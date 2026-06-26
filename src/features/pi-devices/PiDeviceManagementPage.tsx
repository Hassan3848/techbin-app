import React, { useEffect, useMemo, useState } from "react";
import { CheckCircle2, CircleOff, Cpu, KeyRound, RefreshCw, ShieldAlert } from "lucide-react";
import { useAuth } from "../../app/providers/AuthProvider";
import { supabase, type BinRow, type PiDeviceRow } from "../../shared/supabase";
import { formatPipelineTime } from "../../shared/realtimePipeline";

type DeviceRecord = {
  id: string;
  binId: string;
  orgId: string;
  binCode: string;
  deviceName: string;
  active: boolean;
  lastSeen: string | null;
  createdAt: string | null;
};

type CreatedDevice = {
  id: string;
  deviceName: string;
  binCode: string;
  orgId: string;
  token: string;
};

function mapDevice(row: PiDeviceRow): DeviceRecord {
  return {
    id: row.id,
    binId: row.bin_id,
    orgId: row.org_id,
    binCode: row.bin_code,
    deviceName: row.device_name,
    active: row.active,
    lastSeen: row.last_seen,
    createdAt: row.created_at,
  };
}

export const PiDeviceManagementPage: React.FC = () => {
  const { user } = useAuth();
  const isSuperAdmin = user?.superAdmin === true;

  const [devices, setDevices] = useState<DeviceRecord[]>([]);
  const [bins, setBins] = useState<BinRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [deviceName, setDeviceName] = useState("");
  const [selectedBinId, setSelectedBinId] = useState("");
  const [createdDevice, setCreatedDevice] = useState<CreatedDevice | null>(null);
  const [statusText, setStatusText] = useState("");
  const [statusError, setStatusError] = useState(false);

  useEffect(() => {
    if (!isSuperAdmin) {
      setDevices([]);
      setBins([]);
      setLoading(false);
      return;
    }

    let active = true;

    const load = async () => {
      setLoading(true);
      const [{ data: deviceRows, error: deviceError }, { data: binRows, error: binError }] = await Promise.all([
        supabase.from("pi_devices").select("*").order("created_at", { ascending: false }),
        supabase.from("bins").select("*").order("created_at", { ascending: false }),
      ]);

      if (!active) return;

      if (deviceError || binError) {
        console.error(deviceError || binError);
        setStatusText("Pi devices could not be loaded.");
        setStatusError(true);
        setLoading(false);
        return;
      }

      const mappedBins = (binRows || []) as BinRow[];
      setDevices(((deviceRows || []) as PiDeviceRow[]).map(mapDevice));
      setBins(mappedBins);
      setSelectedBinId((current) => current || mappedBins[0]?.id || "");
      setLoading(false);
    };

    load();

    const channel = supabase
      .channel("pi-devices-preview")
      .on("postgres_changes", { event: "*", schema: "public", table: "pi_devices" }, () => load())
      .on("postgres_changes", { event: "*", schema: "public", table: "bins" }, () => load())
      .subscribe();

    return () => {
      active = false;
      supabase.removeChannel(channel);
    };
  }, [isSuperAdmin]);

  const selectedBin = useMemo(() => bins.find((bin) => bin.id === selectedBinId) || null, [bins, selectedBinId]);

  const handleCreateDevice = async () => {
    if (!selectedBinId) return;
    if (!deviceName.trim()) {
      setStatusText("Device name is required.");
      setStatusError(true);
      return;
    }

    setCreating(true);
    setStatusText("");
    setStatusError(false);

    try {
      const { data, error } = await supabase.functions.invoke("admin-create-pi-device", {
        body: {
          binId: selectedBinId,
          deviceName: deviceName.trim(),
        },
      });

      if (error) throw error;
      setCreatedDevice(data as CreatedDevice);
      setDeviceName("");
      setStatusText("Pi device created.");
      setStatusError(false);
    } catch (error) {
      console.error(error);
      setStatusText("Pi device could not be created.");
      setStatusError(true);
    } finally {
      setCreating(false);
    }
  };

  const handleToggleDevice = async (device: DeviceRecord) => {
    setBusyId(device.id);
    setStatusText("");
    setStatusError(false);

    try {
      const { error } = await supabase.functions.invoke("admin-update-pi-device", {
        body: {
          deviceId: device.id,
          active: !device.active,
        },
      });

      if (error) throw error;
      setStatusText(`${device.deviceName} ${device.active ? "deactivated" : "activated"}.`);
      setStatusError(false);
    } catch (error) {
      console.error(error);
      setStatusText("Device status could not be updated.");
      setStatusError(true);
    } finally {
      setBusyId(null);
    }
  };

  if (!isSuperAdmin) {
    return (
      <div className="rounded-xl border border-gray-100 bg-white p-6">
        <h1 className="text-xl text-gray-900">Pi Devices</h1>
        <p className="mt-2 text-sm text-gray-600">Only the TechBin Super Admin can manage Pi credentials.</p>
      </div>
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6">
      <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-2xl text-gray-900">Pi Devices</h1>
          <p className="mt-1 text-sm text-gray-600">
            Provision a device token for a bin. The raw token is shown once and only its hash is stored.
          </p>
        </div>
        <div className="rounded-lg border border-gray-200 bg-white px-4 py-3 text-sm text-gray-700 shadow-sm">
          <div className="font-medium text-gray-900">Preview module</div>
          <div className="text-xs text-gray-500">Hide instantly with `VITE_ENABLE_PI_DEVICES=false`</div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-[420px_1fr]">
        <section className="rounded-xl border border-gray-100 bg-white p-5 shadow-sm">
          <div className="mb-4 flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-emerald-50">
              <KeyRound className="h-5 w-5 text-emerald-600" />
            </div>
            <div>
              <h2 className="text-lg text-gray-900">Create Device Token</h2>
              <p className="text-xs text-gray-500">Provision one Pi against one bin.</p>
            </div>
          </div>

          <div className="space-y-4">
            <div>
              <label className="mb-2 block text-sm text-gray-700">Device name</label>
              <input
                value={deviceName}
                onChange={(event) => setDeviceName(event.target.value)}
                disabled={loading || creating}
                className="w-full rounded-lg border border-gray-300 px-4 py-2 focus:outline-none focus:ring-2 focus:ring-emerald-500 disabled:opacity-60"
                placeholder="BIN-001 Main Pi"
              />
            </div>

            <div>
              <label className="mb-2 block text-sm text-gray-700">Linked bin</label>
              <select
                value={selectedBinId}
                onChange={(event) => setSelectedBinId(event.target.value)}
                disabled={loading || creating}
                className="w-full rounded-lg border border-gray-300 bg-white px-4 py-2 focus:outline-none focus:ring-2 focus:ring-emerald-500 disabled:opacity-60"
              >
                <option value="">Select a bin</option>
                {bins.map((bin) => (
                  <option key={bin.id} value={bin.id}>
                    {bin.bin_code} · {bin.location || bin.org_id}
                  </option>
                ))}
              </select>
            </div>

            {selectedBin && (
              <div className="rounded-lg border border-gray-200 bg-gray-50 p-3 text-sm text-gray-700">
                <div className="font-medium text-gray-900">{selectedBin.bin_code}</div>
                <div>{selectedBin.location || selectedBin.org_id}</div>
              </div>
            )}

            <button
              type="button"
              onClick={handleCreateDevice}
              disabled={loading || creating || !selectedBinId || !deviceName.trim()}
              className="inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-lg bg-emerald-600 px-4 text-white transition-colors hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {creating ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Cpu className="h-4 w-4" />}
              {creating ? "Creating..." : "Generate Device Token"}
            </button>
          </div>
        </section>

        <section className="space-y-5">
          {createdDevice && (
            <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-5 shadow-sm">
              <h2 className="text-lg text-emerald-900">Copy This Token Now</h2>
              <p className="mt-1 text-sm text-emerald-800">
                This is shown once for `{createdDevice.deviceName}` on `{createdDevice.binCode}`.
              </p>
              <div className="mt-4 overflow-x-auto rounded-lg border border-emerald-200 bg-white px-4 py-3 font-mono text-sm text-gray-900">
                {createdDevice.token}
              </div>
            </div>
          )}

          <div className="rounded-xl border border-gray-100 bg-white shadow-sm">
            <div className="flex items-center justify-between border-b border-gray-100 px-5 py-4">
              <div>
                <h2 className="text-lg text-gray-900">Provisioned Devices</h2>
                <p className="text-xs text-gray-500">Cloud-side credentials mapped to bins.</p>
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full min-w-[640px]">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-5 py-3 text-left text-xs uppercase tracking-wider text-gray-600">Device</th>
                    <th className="px-5 py-3 text-left text-xs uppercase tracking-wider text-gray-600">Bin</th>
                    <th className="px-5 py-3 text-left text-xs uppercase tracking-wider text-gray-600">Status</th>
                    <th className="px-5 py-3 text-left text-xs uppercase tracking-wider text-gray-600">Last Seen</th>
                    <th className="px-5 py-3 text-right text-xs uppercase tracking-wider text-gray-600">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {loading ? (
                    <tr>
                      <td className="px-5 py-5 text-sm text-gray-600" colSpan={5}>Loading devices...</td>
                    </tr>
                  ) : devices.length === 0 ? (
                    <tr>
                      <td className="px-5 py-6 text-sm text-gray-600" colSpan={5}>
                        No Pi devices are provisioned yet. Create one for `BIN-001` to start the preview flow.
                      </td>
                    </tr>
                  ) : (
                    devices.map((device) => (
                      <tr key={device.id} className="hover:bg-gray-50">
                        <td className="px-5 py-4 text-sm">
                          <div className="font-medium text-gray-900">{device.deviceName}</div>
                          <div className="text-xs text-gray-500">{device.orgId}</div>
                        </td>
                        <td className="px-5 py-4 text-sm text-gray-700">{device.binCode}</td>
                        <td className="px-5 py-4 text-sm">
                          <span
                            className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs ${
                              device.active ? "bg-emerald-100 text-emerald-800" : "bg-gray-100 text-gray-700"
                            }`}
                          >
                            {device.active ? <CheckCircle2 className="h-3.5 w-3.5" /> : <CircleOff className="h-3.5 w-3.5" />}
                            {device.active ? "Active" : "Inactive"}
                          </span>
                        </td>
                        <td className="px-5 py-4 text-sm text-gray-700">{formatPipelineTime(device.lastSeen)}</td>
                        <td className="px-5 py-4 text-right">
                          <button
                            type="button"
                            onClick={() => handleToggleDevice(device)}
                            disabled={busyId === device.id}
                            className="inline-flex min-h-10 items-center justify-center rounded-lg border border-gray-200 px-4 text-sm text-gray-700 transition-colors hover:bg-gray-50 disabled:opacity-60"
                          >
                            {busyId === device.id ? "Updating..." : device.active ? "Deactivate" : "Activate"}
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
            <div className="flex items-start gap-3">
              <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0" />
              <div>
                The Pi should send real-world values to the cloud using `x-device-token`. The web app reads only from Supabase and never directly from the Raspberry Pi.
              </div>
            </div>
          </div>

          <p className={`min-h-5 text-sm ${statusError ? "text-red-600" : "text-emerald-700"}`}>{statusText}</p>
        </section>
      </div>
    </div>
  );
};
