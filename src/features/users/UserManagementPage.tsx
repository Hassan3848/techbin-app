import React, { useEffect, useMemo, useState } from "react";
import { UserPlus, Shield, Eye, Trash2 } from "lucide-react";
import { supabase, type ProfileRow } from "../../shared/supabase";
import { useAuth } from "../../app/providers/AuthProvider";

type Role = "Admin" | "Viewer";

type UserDoc = {
  email: string;
  displayName?: string | null;
  role: Role;
  orgId: string;
  superAdmin?: boolean;
  disabled?: boolean;
  createdAt?: any;
  createdBy?: string;
};

function mapProfile(row: ProfileRow): { id: string } & UserDoc {
  return {
    id: row.id,
    email: row.email,
    displayName: row.display_name,
    role: row.role === "Admin" ? "Admin" : "Viewer",
    orgId: row.org_id,
    superAdmin: row.super_admin,
    disabled: row.disabled,
    createdAt: row.created_at,
    createdBy: row.created_by || undefined,
  };
}

export const UserManagementPage: React.FC = () => {
  const { user } = useAuth();
  const isAdmin = user?.role === "Admin";
  const isSuperAdmin = user?.superAdmin === true;

  const [showCreateModal, setShowCreateModal] = useState(false);
  const [busy, setBusy] = useState(false);

  const [users, setUsers] = useState<Array<{ id: string } & UserDoc>>([]);

  const [newEmail, setNewEmail] = useState("");
  const [newRole, setNewRole] = useState<Role>("Viewer");
  const [newPassword, setNewPassword] = useState("");

  // only superAdmin can choose orgId; org admin forced to their org
  const [newOrgId, setNewOrgId] = useState("");

  useEffect(() => {
    if (!isAdmin || !user) {
      setUsers([]);
      return;
    }

    const loadUsers = async () => {
      let request = supabase
        .from("profiles")
        .select("*")
        .order("created_at", { ascending: false });

      if (!isSuperAdmin) request = request.eq("org_id", user.orgId).eq("super_admin", false);

      const { data, error } = await request;
      if (error) {
        console.error(error);
        alert("Failed to load users. Check Supabase RLS policies.");
        return;
      }

      setUsers(((data || []) as ProfileRow[]).map(mapProfile));
    };

    loadUsers();

    const channel = supabase
      .channel(`profiles:${isSuperAdmin ? "all" : user.orgId}`)
      .on("postgres_changes", { event: "*", schema: "public", table: "profiles" }, () => loadUsers())
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, [isAdmin, isSuperAdmin, user?.orgId]);

  const activeCount = useMemo(() => users.filter((u) => !u.disabled).length, [users]);
  const adminCount = useMemo(() => users.filter((u) => u.role === "Admin").length, [users]);
  const viewerCount = useMemo(() => users.filter((u) => u.role === "Viewer").length, [users]);

  const handleCreateUser = async () => {
    const email = newEmail.trim().toLowerCase();
    const password = newPassword;

    if (!email) return alert("Email is required.");
    if (password.length < 6) return alert("Password must be at least 6 characters.");

    setBusy(true);
    try {
      const payload: any = { email, password, role: newRole };
      if (isSuperAdmin) {
        const orgId = newOrgId.trim().toLowerCase();
        if (orgId) payload.orgId = orgId;
      }

      const { error } = await supabase.functions.invoke("admin-create-user", { body: payload });
      if (error) throw error;

      setShowCreateModal(false);
      setNewEmail("");
      setNewPassword("");
      setNewRole("Viewer");
      setNewOrgId("");

      alert("User created.");
    } catch (e: any) {
      console.error(e);
      alert(e?.message || "Create user failed.");
    } finally {
      setBusy(false);
    }
  };

  const handleDeleteUser = async (uid: string, email: string) => {
    if (email?.toLowerCase() === user?.email?.toLowerCase()) {
      return alert("You cannot delete your own account.");
    }

    const ok = window.confirm(`Delete this user?\n\n${email}\n\nThis will remove them from Supabase Auth + profile.`);
    if (!ok) return;

    setBusy(true);
    try {
      const { error } = await supabase.functions.invoke("admin-delete-user", { body: { uid, email } });
      if (error) throw error;
      alert("User deleted.");
    } catch (e: any) {
      console.error(e);
      alert(e?.message || "Delete failed.");
    } finally {
      setBusy(false);
    }
  };

  const canDeleteUser = (row: { id: string } & UserDoc) => {
    if (busy) return false;
    if (row.email?.toLowerCase() === user?.email?.toLowerCase()) return false;
    if (row.superAdmin) return false;
    if (isSuperAdmin) return true;
    return row.role === "Viewer";
  };

  const deleteTitle = (row: { id: string } & UserDoc) => {
    if (row.email?.toLowerCase() === user?.email?.toLowerCase()) return "Can't delete yourself";
    if (row.superAdmin) return "Super admin cannot be deleted";
    if (!isSuperAdmin && row.role !== "Viewer") return "Org admins can delete viewers only";
    return "Delete";
  };

  if (!isAdmin) {
    return (
      <div className="bg-white rounded-xl border border-gray-100 p-6">
        <h1 className="text-xl text-gray-900 mb-2">User Management</h1>
        <p className="text-gray-600">You do not have permission to access this page.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="text-2xl text-gray-900 mb-2">User Management</h1>
          <p className="text-gray-600">
            {isSuperAdmin ? "Super Admin: managing all organizations" : `Org Admin: ${user?.orgId}`}
          </p>
        </div>

        <button
          onClick={() => setShowCreateModal(true)}
          disabled={busy}
          className="flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg transition-colors disabled:opacity-60"
        >
          <UserPlus className="w-5 h-5" />
          Create User
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-white rounded-xl shadow-sm p-6 border border-gray-100">
          <p className="text-3xl text-emerald-600">{activeCount}</p>
          <p className="text-sm text-gray-600">Active Users</p>
        </div>
        <div className="bg-white rounded-xl shadow-sm p-6 border border-gray-100">
          <p className="text-3xl text-blue-600">{adminCount}</p>
          <p className="text-sm text-gray-600">Administrators</p>
        </div>
        <div className="bg-white rounded-xl shadow-sm p-6 border border-gray-100">
          <p className="text-3xl text-gray-600">{viewerCount}</p>
          <p className="text-sm text-gray-600">Viewers</p>
        </div>
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="px-6 py-4 text-left text-xs text-gray-600 uppercase tracking-wider">Email</th>
                {isSuperAdmin && (
                  <th className="px-6 py-4 text-left text-xs text-gray-600 uppercase tracking-wider">Org</th>
                )}
                <th className="px-6 py-4 text-left text-xs text-gray-600 uppercase tracking-wider">Role</th>
                <th className="px-6 py-4 text-left text-xs text-gray-600 uppercase tracking-wider">Status</th>
                <th className="px-6 py-4 text-right text-xs text-gray-600 uppercase tracking-wider">Actions</th>
              </tr>
            </thead>

            <tbody className="divide-y divide-gray-200">
              {users.map((u) => (
                <tr key={u.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">{u.email}</td>

                  {isSuperAdmin && (
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-700">{u.orgId}</td>
                  )}

                  <td className="px-6 py-4 whitespace-nowrap">
                    <span
                      className={`inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs ${
                        u.role === "Admin" ? "bg-blue-100 text-blue-800" : "bg-gray-100 text-gray-800"
                      }`}
                    >
                      {u.role === "Admin" ? <Shield className="w-3 h-3" /> : <Eye className="w-3 h-3" />}
                      {u.role}
                    </span>
                  </td>

                  <td className="px-6 py-4 whitespace-nowrap">
                    <span
                      className={`inline-flex items-center px-3 py-1 rounded-full text-xs ${
                        u.disabled ? "bg-red-100 text-red-800" : "bg-green-100 text-green-800"
                      }`}
                    >
                      {u.disabled ? "Disabled" : "Active"}
                    </span>
                  </td>

                  <td className="px-6 py-4 whitespace-nowrap text-right">
                    <button
                      onClick={() => handleDeleteUser(u.id, u.email)}
                      disabled={!canDeleteUser(u)}
                      className="inline-flex items-center gap-2 px-3 py-2 text-sm border border-red-200 text-red-700 rounded-lg hover:bg-red-50 disabled:opacity-50"
                      title={deleteTitle(u)}
                    >
                      <Trash2 className="w-4 h-4" />
                      Delete
                    </button>
                  </td>
                </tr>
              ))}

              {users.length === 0 && (
                <tr>
                  <td className="px-6 py-6 text-sm text-gray-600" colSpan={isSuperAdmin ? 5 : 4}>
                    No users found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {showCreateModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl max-w-md w-full p-6">
            <h2 className="text-xl text-gray-900 mb-4">Create New User</h2>

            <div className="space-y-4">
              <div>
                <label className="block text-sm text-gray-700 mb-2">Email</label>
                <input
                  type="email"
                  value={newEmail}
                  onChange={(e) => setNewEmail(e.target.value)}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  placeholder="user@techbin.com"
                />
              </div>

              {isSuperAdmin && (
                <div>
                  <label className="block text-sm text-gray-700 mb-2">Org ID (optional)</label>
                  <input
                    value={newOrgId}
                    onChange={(e) => setNewOrgId(e.target.value)}
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500"
                    placeholder="evergreen (leave empty to infer from email)"
                  />
                  <p className="text-xs text-gray-500 mt-1">
                    Only Super Admin can set org explicitly. Org Admins are forced to their org.
                  </p>
                </div>
              )}

              <div>
                <label className="block text-sm text-gray-700 mb-2">Role</label>
                <select
                  value={newRole}
                  onChange={(e) => setNewRole(e.target.value === "Admin" ? "Admin" : "Viewer")}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500"
                >
                  <option value="Viewer">Viewer</option>
                  {isSuperAdmin && <option value="Admin">Admin</option>}
                </select>
              </div>

              <div>
                <label className="block text-sm text-gray-700 mb-2">Initial Password</label>
                <input
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  placeholder="Enter password (min 6 chars)"
                />
              </div>
            </div>

            <div className="flex gap-3 mt-6">
              <button
                onClick={() => setShowCreateModal(false)}
                disabled={busy}
                className="flex-1 px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors disabled:opacity-60"
              >
                Cancel
              </button>
              <button
                onClick={handleCreateUser}
                disabled={busy}
                className="flex-1 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg transition-colors disabled:opacity-60"
              >
                {busy ? "Working..." : "Create User"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
