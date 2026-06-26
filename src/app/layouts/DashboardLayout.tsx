import React, { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../providers/AuthProvider";
import {
  LayoutDashboard,
  BarChart3,
  Activity,
  TriangleAlert,
  Cpu,
  Users,
  Settings,
  HardDrive,
  LogOut,
  Menu,
  X,
  Recycle,
  Trash2,
} from "lucide-react";
import { featureFlags } from "../../shared/features";

export const DashboardLayout: React.FC = () => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const handleLogout = () => {
    logout();
    navigate("/");
  };

  const isAdmin = user?.role === "Admin";
  const isSuperAdmin = user?.superAdmin === true;

  const navigationItems = [
    {
      name: "Dashboard Overview",
      path: "/dashboard",
      icon: LayoutDashboard,
    },
    {
      name: "Analytics",
      path: "/dashboard/analytics",
      icon: BarChart3,
    },
    {
      name: "Real-Time Monitoring",
      path: "/dashboard/monitoring",
      icon: Activity,
    },
    {
      name: "Fault Detection",
      path: "/dashboard/faults",
      icon: TriangleAlert,
    },
    {
      name: "Bin Health Status",
      path: "/dashboard/health",
      icon: Cpu,
    },

    // ✅ Always visible (label changes by org role)
    {
      name: isSuperAdmin ? "Bin Registry" : "Your Bins",
      path: "/dashboard/bins",
      icon: Trash2,
    },

    ...(isAdmin
      ? [
          {
            name: "User Management",
            path: "/dashboard/users",
            icon: Users,
          },
        ]
      : []),

    ...(featureFlags.piDevices && isSuperAdmin
      ? [
          {
            name: "Pi Devices",
            path: "/dashboard/devices",
            icon: HardDrive,
          },
        ]
      : []),

    {
      name: "Settings",
      path: "/dashboard/settings",
      icon: Settings,
    },
  ];

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Top Navigation Bar */}
      <div className="fixed top-0 left-0 right-0 h-16 bg-white border-b border-gray-200 z-50">
        <div className="flex items-center justify-between h-full px-4">
          <div className="flex items-center gap-4">
            <button
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className="lg:hidden text-gray-600 hover:text-emerald-600"
            >
              {sidebarOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
            </button>
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-emerald-600 rounded-lg flex items-center justify-center">
                <Recycle className="w-6 h-6 text-white" />
              </div>
              <span className="text-xl text-emerald-900">TechBin Dashboard</span>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <div className="text-right hidden sm:block">
              <div className="text-sm text-gray-900">{user?.email}</div>
              <div className="text-xs text-emerald-600">
                {isSuperAdmin ? "Super Admin" : user?.role}
              </div>
            </div>
            <button
              onClick={handleLogout}
              className="flex items-center gap-2 px-4 py-2 text-gray-700 hover:text-emerald-600 hover:bg-emerald-50 rounded-lg transition-colors"
            >
              <LogOut className="w-5 h-5" />
              <span className="hidden sm:inline">Logout</span>
            </button>
          </div>
        </div>
      </div>

      {/* Sidebar */}
      <aside
        className={`fixed top-16 left-0 bottom-0 w-64 bg-white border-r border-gray-200 transition-transform duration-300 z-40 ${
          sidebarOpen ? "translate-x-0" : "-translate-x-full"
        } lg:translate-x-0`}
      >
        <nav className="p-4 space-y-1">
          {navigationItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.path === "/dashboard"}
              onClick={() => setSidebarOpen(false)}
              className={({ isActive }) =>
                `flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${
                  isActive ? "bg-emerald-50 text-emerald-600" : "text-gray-700 hover:bg-gray-100"
                }`
              }
            >
              <item.icon className="w-5 h-5" />
              <span>{item.name}</span>
            </NavLink>
          ))}
        </nav>
      </aside>

      {/* Mobile sidebar overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-30 lg:hidden top-16"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Main Content */}
      <main className="pt-16 lg:pl-64">
        <div className="p-6">
          <Outlet />
        </div>
      </main>
    </div>
  );
};
