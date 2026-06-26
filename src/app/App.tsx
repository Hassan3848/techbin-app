import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './providers/AuthProvider';
import { SettingsProvider } from './providers/SettingsProvider';
import { LoginPage } from '../features/auth/LoginPage';
import { DashboardLayout } from './layouts/DashboardLayout';
import { ProtectedRoute } from './routing/ProtectedRoute';
import { DashboardOverview } from '../features/dashboard/DashboardOverview';
import { AnalyticsPage } from '../features/analytics/AnalyticsPage';
import { RealTimeMonitoringPage } from '../features/monitoring/RealTimeMonitoringPage';
import { FaultDetectionPage } from '../features/faults/FaultDetectionPage';
import { BinHealthStatusPage } from '../features/bin-health/BinHealthStatusPage';
import { UserManagementPage } from '../features/users/UserManagementPage';
import { SettingsPage } from '../features/settings/SettingsPage';
import { PiDeviceManagementPage } from "../features/pi-devices/PiDeviceManagementPage";
import BinRegistryPage from "../features/bins/BinRegistryPage";
import { featureFlags } from "../shared/features";

export default function App() {
  return (
    <AuthProvider>
      <SettingsProvider>
        <BrowserRouter>
          <Routes>
            {/* Public Route */}
            <Route path="/" element={<LoginPage />} />

            {/* Protected Dashboard Routes */}
            <Route
              path="/dashboard"
              element={
                <ProtectedRoute>
                  <DashboardLayout />
                </ProtectedRoute>
              }
            >
              <Route index element={<DashboardOverview />} />
              <Route path="analytics" element={<AnalyticsPage />} />
              <Route path="monitoring" element={<RealTimeMonitoringPage />} />
              <Route path="faults" element={<FaultDetectionPage />} />
              <Route path="health" element={<BinHealthStatusPage />} />

              {/* ✅ Bins: allow ALL signed-in users (Viewer can view, Admin can edit, SuperAdmin can create/delete) */}
              <Route
                path="bins"
                element={
                  <ProtectedRoute>
                    <BinRegistryPage />
                  </ProtectedRoute>
                }
              />

              {/* ✅ Admin-only */}
              <Route
                path="users"
                element={
                  <ProtectedRoute requireAdmin>
                    <UserManagementPage />
                  </ProtectedRoute>
                }
              />

              <Route path="settings" element={<SettingsPage />} />
              {featureFlags.piDevices && (
                <Route
                  path="devices"
                  element={
                    <ProtectedRoute requireAdmin>
                      <PiDeviceManagementPage />
                    </ProtectedRoute>
                  }
                />
              )}
            </Route>

            {/* Catch all - redirect to login */}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </SettingsProvider>
    </AuthProvider>
  );
}
