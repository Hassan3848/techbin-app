import React from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../providers/AuthProvider";

interface ProtectedRouteProps {
  children: React.ReactNode;
  requireAdmin?: boolean;
}

export const ProtectedRoute: React.FC<ProtectedRouteProps> = ({
  children,
  requireAdmin = false,
}) => {
  const { isAuthenticated, user, loading } = useAuth();

  // Prevent redirect flicker while Supabase is still checking session
  if (loading) {
    return (
      <div className="min-h-[40vh] flex items-center justify-center text-gray-600">
        Loading...
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/" replace />;
  }

  if (requireAdmin && user?.role !== "Admin") {
    return <Navigate to="/dashboard" replace />;
  }

  return <>{children}</>;
};
