import React, { useEffect, useMemo, useState } from "react";
import { Plus, Trash2, Pencil, MapPin, AlertTriangle } from "lucide-react";
import { supabase, type BinRow } from "../../shared/supabase";
import { useAuth } from "../../app/providers/AuthProvider";

type BinStatus = "Active" | "Maintenance" | "Inactive";

type BinDoc = {
  orgId: string;
  binCode: string; // e.g. BIN-001
  location?: string | null;
  status: BinStatus;
  capacityLiters?: number | null;

  createdAt?: any;
  createdBy?: string | null;
  updatedAt?: any;
  updatedBy?: string | null;
};

function makeBinId(orgId: string, binCode: string) {
  return `${orgId}_${binCode.trim().toUpperCase()}`;
}

function mapBin(row: BinRow): { id: string } & BinDoc {
  return {
    id: row.id,
    orgId: row.org_id,
    binCode: row.bin_code,
    location: row.location,
    status: row.status,
    capacityLiters: row.capacity_liters,
    createdAt: row.created_at,
    createdBy: row.created_by,
    updatedAt: row.updated_at,
    updatedBy: row.updated_by,
  };
}

export const BinRegistryPage: React.FC = () => {
  const { user } = useAuth();

  const isSignedIn = !!user;

  // Your AuthContext uses `role` and `superAdmin`
  const isAdmin = user?.role === "Admin";
  const isSuperAdmin = user?.superAdmin === true;

  // ✅ Policy
  const canCreate = isSuperAdmin; // only TechBin Super Admin provisions bins
  const canDelete = isSuperAdmin; // only TechBin Super Admin deletes bins
  const canEdit = isAdmin; // Admin (including Super Admin) can edit location/status/capacity

  const myOrgId = user?.orgId?.trim() ? user.orgId : "techbin";

  const [bins, setBins] = useState<Array<{ id: string } & BinDoc>>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const [search, setSearch] = useState("");

  // Create modal
  const [showCreate, setShowCreate] = useState(false);
  const [newOrgId, setNewOrgId] = useState("");
  const [newBinCode, setNewBinCode] = useState("");
  const [newLocation, setNewLocation] = useState("");
  const [newStatus, setNewStatus] = useState<BinStatus>("Active");
  const [newCapacity, setNewCapacity] = useState<string>("");

  // Edit modal
  const [showEdit, setShowEdit] = useState(false);
  const [editing, setEditing] = useState<({ id: string } & BinDoc) | null>(null);

  const [editLocation, setEditLocation] = useState("");
  const [editStatus, setEditStatus] = useState<BinStatus>("Active");
  const [editCapacity, setEditCapacity] = useState<string>("");

  // Realtime load (multi-tenant)
  useEffect(() => {
    if (!isSignedIn || !user) {
      setBins([]);
      setLoading(false);
      return;
    }

    setLoading(true);

    const loadBins = async () => {
      let request = supabase
        .from("bins")
        .select("*")
        .order("created_at", { ascending: false });

      if (!isSuperAdmin) request = request.eq("org_id", myOrgId);

      const { data, error } = await request;
      if (error) {
        console.error("bins load error:", error);
        setLoading(false);
        alert("Failed to load bins. Check Supabase RLS policies.");
        return;
      }

      setBins(((data || []) as BinRow[]).map(mapBin));
      setLoading(false);
    };

    loadBins();

    const channel = supabase
      .channel(`bins:${isSuperAdmin ? "all" : myOrgId}`)
      .on("postgres_changes", { event: "*", schema: "public", table: "bins" }, () => loadBins())
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, [isSignedIn, isSuperAdmin, myOrgId, user]);

  const filteredBins = useMemo(() => {
    const s = search.trim().toLowerCase();
    if (!s) return bins;

    return bins.filter((b) => {
      const hay = `${b.binCode} ${b.location || ""} ${b.status} ${b.orgId}`.toLowerCase();
      return hay.includes(s);
    });
  }, [bins, search]);

  const totalBins = bins.length;
  const activeBins = useMemo(() => bins.filter((b) => b.status === "Active").length, [bins]);
  const maintenanceBins = useMemo(
    () => bins.filter((b) => b.status === "Maintenance").length,
    [bins]
  );

  const resetCreate = () => {
    setNewOrgId("");
    setNewBinCode("");
    setNewLocation("");
    setNewStatus("Active");
    setNewCapacity("");
  };

  const openEditModal = (row: { id: string } & BinDoc) => {
    setEditing(row);
    setEditLocation(row.location || "");
    setEditStatus(row.status || "Active");
    setEditCapacity(row.capacityLiters != null ? String(row.capacityLiters) : "");
    setShowEdit(true);
  };

  const handleCreateBin = async () => {
    if (!user) return;
    if (!canCreate) return alert("Only TechBin Super Admin can create/provision bins.");

    const binCode = newBinCode.trim().toUpperCase();
    if (!binCode) return alert("Bin Code is required (e.g., BIN-001).");

    // Super Admin can provision bins for any org
    const orgId = (newOrgId.trim().toLowerCase() || myOrgId).trim();
    if (!orgId) return alert("Org ID is required.");

    const binId = makeBinId(orgId, binCode);

    const cap = newCapacity.trim() ? Number(newCapacity.trim()) : null;
    if (newCapacity.trim() && Number.isNaN(cap)) return alert("Capacity must be a number (liters).");

    // ✅ location is optional now (sub-org can fill later)
    const location = newLocation.trim();
    const locationValue = location ? location : null;

    setBusy(true);
    try {
      const { data: existing, error: lookupError } = await supabase
        .from("bins")
        .select("id")
        .eq("id", binId)
        .maybeSingle();

      if (lookupError) throw lookupError;
      if (existing) {
        return alert(`A bin with code "${binCode}" already exists in org "${orgId}".`);
      }

      const payload = {
        id: binId,
        org_id: orgId,
        bin_code: binCode,
        location: locationValue,
        status: newStatus,
        capacity_liters: cap,
        created_by: user.email || null,
      };

      const { error } = await supabase.from("bins").insert(payload);
      if (error) throw error;

      setShowCreate(false);
      resetCreate();
      alert("Bin provisioned.");
    } catch (e: any) {
      console.error(e);
      alert(e?.message || "Create bin failed.");
    } finally {
      setBusy(false);
    }
  };

  const handleUpdateBin = async () => {
    if (!editing) return;
    if (!user) return;
    if (!canEdit) return alert("Only Admin can update bins.");

    const cap = editCapacity.trim() ? Number(editCapacity.trim()) : null;
    if (editCapacity.trim() && Number.isNaN(cap)) return alert("Capacity must be a number (liters).");

    // location is allowed to be empty (null)
    const location = editLocation.trim();
    const locationValue = location ? location : null;

    setBusy(true);
    try {
      const { error } = await supabase
        .from("bins")
        .update({
          location: locationValue,
          status: editStatus,
          capacity_liters: cap,
          updated_at: new Date().toISOString(),
          updated_by: user.email || null,
        })
        .eq("id", editing.id);

      if (error) throw error;

      setShowEdit(false);
      setEditing(null);
      alert("Bin updated.");
    } catch (e: any) {
      console.error(e);
      alert(e?.message || "Update failed.");
    } finally {
      setBusy(false);
    }
  };

  const handleDeleteBin = async (row: { id: string } & BinDoc) => {
    if (!user) return;
    if (!canDelete) return alert("Only TechBin Super Admin can delete bins.");

    const ok = window.confirm(`Delete bin "${row.binCode}" (Org: ${row.orgId})? This cannot be undone.`);
    if (!ok) return;

    setBusy(true);
    try {
      const { error } = await supabase.from("bins").delete().eq("id", row.id);
      if (error) throw error;
      alert("Bin deleted.");
    } catch (e: any) {
      console.error(e);
      alert(e?.message || "Delete failed.");
    } finally {
      setBusy(false);
    }
  };

  if (!isSignedIn) {
    return (
      <div className="bg-white rounded-xl border border-gray-100 p-6">
        <h1 className="text-xl text-gray-900 mb-2">Bins</h1>
        <p className="text-gray-600">Please login to view bins.</p>
      </div>
    );
  }

  const pageTitle = isSuperAdmin ? "Bin Registry" : "Your Bins";
  const subtitle = isSuperAdmin ? "Super Admin: viewing all organizations" : `Org: ${myOrgId}`;

  return (
    <div className="bg-white rounded-xl border border-gray-100 p-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl text-gray-900">{pageTitle}</h1>
          <p className="text-sm text-gray-600">{subtitle}</p>
        </div>

        <div className="flex items-center gap-2">
          <input
            className="w-64 max-w-full px-3 py-2 border border-gray-200 rounded-lg outline-none focus:border-emerald-500"
            placeholder="Search bins..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />

          {canCreate && (
            <button
              onClick={() => setShowCreate(true)}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-emerald-600 text-white hover:bg-emerald-700"
            >
              <Plus className="w-4 h-4" />
              Add Bin
            </button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-5">
        <div className="rounded-xl border border-gray-100 p-4">
          <div className="text-sm text-gray-600">Total Bins</div>
          <div className="text-2xl text-gray-900">{totalBins}</div>
        </div>
        <div className="rounded-xl border border-gray-100 p-4">
          <div className="text-sm text-gray-600">Active</div>
          <div className="text-2xl text-gray-900">{activeBins}</div>
        </div>
        <div className="rounded-xl border border-gray-100 p-4">
          <div className="text-sm text-gray-600">Maintenance</div>
          <div className="text-2xl text-gray-900">{maintenanceBins}</div>
        </div>
      </div>

      <div className="mt-6">
        {loading ? (
          <div className="text-gray-600">Loading bins...</div>
        ) : filteredBins.length === 0 ? (
          <div className="text-gray-600">No bins found.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="text-left text-gray-600 border-b">
                  {isSuperAdmin && <th className="py-3 pr-4">Org</th>}
                  <th className="py-3 pr-4">Code</th>
                  <th className="py-3 pr-4">Location</th>
                  <th className="py-3 pr-4">Status</th>
                  <th className="py-3 pr-4">Capacity (L)</th>
                  {canEdit && <th className="py-3 pr-2">Actions</th>}
                </tr>
              </thead>
              <tbody>
                {filteredBins.map((b) => (
                  <tr key={b.id} className="border-b last:border-b-0">
                    {isSuperAdmin && <td className="py-3 pr-4">{b.orgId}</td>}
                    <td className="py-3 pr-4 font-medium text-gray-900">{b.binCode}</td>
                    <td className="py-3 pr-4 text-gray-700">
                      <span className="inline-flex items-center gap-2">
                        <MapPin className="w-4 h-4 text-gray-400" />
                        {b.location ? b.location : "-"}
                      </span>
                    </td>
                    <td className="py-3 pr-4 text-gray-700">{b.status}</td>
                    <td className="py-3 pr-4 text-gray-700">{b.capacityLiters ?? "-"}</td>

                    {canEdit && (
                      <td className="py-3 pr-2">
                        <div className="flex items-center gap-2">
                          <button
                            className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-gray-200 hover:bg-gray-50"
                            onClick={() => openEditModal(b)}
                            disabled={busy}
                            title="Edit"
                          >
                            <Pencil className="w-4 h-4" />
                            Edit
                          </button>

                          {canDelete && (
                            <button
                              className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-red-200 text-red-700 hover:bg-red-50"
                              onClick={() => handleDeleteBin(b)}
                              disabled={busy}
                              title="Delete"
                            >
                              <Trash2 className="w-4 h-4" />
                              Delete
                            </button>
                          )}
                        </div>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {!isAdmin && (
          <div className="mt-4 flex items-start gap-2 text-sm text-amber-700 bg-amber-50 border border-amber-100 rounded-lg p-3">
            <AlertTriangle className="w-4 h-4 mt-0.5" />
            <div>
              You are logged in as <b>Viewer</b>. You can only view bins.
            </div>
          </div>
        )}
      </div>

      {/* CREATE MODAL (Super Admin only) */}
      {showCreate && canCreate && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-50">
          <div className="w-full max-w-xl bg-white rounded-2xl shadow-xl p-6">
            <h2 className="text-xl text-gray-900 mb-4">Add New Bin</h2>

            <div className="mb-4">
              <label className="text-sm text-gray-700">Org ID (required)</label>
              <input
                className="mt-1 w-full px-3 py-2 border border-gray-200 rounded-lg outline-none focus:border-emerald-500"
                placeholder="evergreen (leave empty = techbin)"
                value={newOrgId}
                onChange={(e) => setNewOrgId(e.target.value)}
              />
              <p className="text-xs text-gray-500 mt-1">
                TechBin Super Admin provisions bins for organizations.
              </p>
            </div>

            <div className="mb-4">
              <label className="text-sm text-gray-700">Bin Code</label>
              <input
                className="mt-1 w-full px-3 py-2 border border-gray-200 rounded-lg outline-none focus:border-emerald-500"
                placeholder="BIN-001"
                value={newBinCode}
                onChange={(e) => setNewBinCode(e.target.value)}
              />
            </div>

            <div className="mb-4">
              <label className="text-sm text-gray-700">Location (optional)</label>
              <input
                className="mt-1 w-full px-3 py-2 border border-gray-200 rounded-lg outline-none focus:border-emerald-500"
                placeholder="Block A, Entrance (optional — org can fill later)"
                value={newLocation}
                onChange={(e) => setNewLocation(e.target.value)}
              />
            </div>

            <div className="mb-4">
              <label className="text-sm text-gray-700">Status</label>
              <select
                className="mt-1 w-full px-3 py-2 border border-gray-200 rounded-lg outline-none focus:border-emerald-500 bg-white"
                value={newStatus}
                onChange={(e) => setNewStatus(e.target.value as BinStatus)}
              >
                <option value="Active">Active</option>
                <option value="Maintenance">Maintenance</option>
                <option value="Inactive">Inactive</option>
              </select>
            </div>

            <div className="mb-6">
              <label className="text-sm text-gray-700">Capacity (liters, optional)</label>
              <input
                className="mt-1 w-full px-3 py-2 border border-gray-200 rounded-lg outline-none focus:border-emerald-500"
                placeholder="120"
                value={newCapacity}
                onChange={(e) => setNewCapacity(e.target.value)}
              />
            </div>

            <div className="flex items-center justify-end gap-3">
              <button
                className="px-4 py-2 rounded-lg border border-gray-200 hover:bg-gray-50"
                onClick={() => {
                  setShowCreate(false);
                  resetCreate();
                }}
                disabled={busy}
              >
                Cancel
              </button>
              <button
                className="px-4 py-2 rounded-lg bg-emerald-600 text-white hover:bg-emerald-700"
                onClick={handleCreateBin}
                disabled={busy}
              >
                {busy ? "Creating..." : "Create"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* EDIT MODAL */}
      {showEdit && editing && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-50">
          <div className="w-full max-w-xl bg-white rounded-2xl shadow-xl p-6">
            <h2 className="text-xl text-gray-900 mb-4">Edit Bin</h2>

            <div className="mb-4">
              <div className="text-sm text-gray-600">Code</div>
              <div className="text-gray-900 font-medium">{editing.binCode}</div>
            </div>

            <div className="mb-4">
              <label className="text-sm text-gray-700">Location</label>
              <input
                className="mt-1 w-full px-3 py-2 border border-gray-200 rounded-lg outline-none focus:border-emerald-500"
                value={editLocation}
                onChange={(e) => setEditLocation(e.target.value)}
              />
              <p className="text-xs text-gray-500 mt-1">
                Only location/status/capacity are editable. OrgId & BinCode cannot be changed.
              </p>
            </div>

            <div className="mb-4">
              <label className="text-sm text-gray-700">Status</label>
              <select
                className="mt-1 w-full px-3 py-2 border border-gray-200 rounded-lg outline-none focus:border-emerald-500 bg-white"
                value={editStatus}
                onChange={(e) => setEditStatus(e.target.value as BinStatus)}
              >
                <option value="Active">Active</option>
                <option value="Maintenance">Maintenance</option>
                <option value="Inactive">Inactive</option>
              </select>
            </div>

            <div className="mb-6">
              <label className="text-sm text-gray-700">Capacity (liters, optional)</label>
              <input
                className="mt-1 w-full px-3 py-2 border border-gray-200 rounded-lg outline-none focus:border-emerald-500"
                value={editCapacity}
                onChange={(e) => setEditCapacity(e.target.value)}
              />
            </div>

            <div className="flex items-center justify-end gap-3">
              <button
                className="px-4 py-2 rounded-lg border border-gray-200 hover:bg-gray-50"
                onClick={() => {
                  setShowEdit(false);
                  setEditing(null);
                }}
                disabled={busy}
              >
                Cancel
              </button>
              <button
                className="px-4 py-2 rounded-lg bg-emerald-600 text-white hover:bg-emerald-700"
                onClick={handleUpdateBin}
                disabled={busy}
              >
                {busy ? "Saving..." : "Save"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default BinRegistryPage;
