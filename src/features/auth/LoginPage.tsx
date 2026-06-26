import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../app/providers/AuthProvider';
import { Recycle } from 'lucide-react';

export const LoginPage: React.FC = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const { login } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (!email || !password) {
      setError('Invalid credentials');
      return;
    }

    const success = await login(email, password);
    if (success) {
      navigate('/dashboard');
    } else {
      setError('Invalid credentials');
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-emerald-50 to-white flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="bg-white rounded-2xl shadow-lg p-8">
          {/* Logo */}
          <div className="flex flex-col items-center mb-8">
            <div className="w-16 h-16 bg-emerald-600 rounded-xl flex items-center justify-center mb-4">
              <Recycle className="w-10 h-10 text-white" />
            </div>
            <h1 className="text-3xl text-emerald-900 mb-2">TechBin Dashboard</h1>
            <p className="text-sm text-gray-600 text-center">
              Authorized Organizational Access Only
            </p>
          </div>

          {/* Login Form */}
          <form onSubmit={handleSubmit} className="space-y-6">
            <div>
              <label htmlFor="email" className="block text-sm text-gray-700 mb-2">
                Email
              </label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent"
                placeholder="Enter your email"
              />
            </div>

            <div>
              <label htmlFor="password" className="block text-sm text-gray-700 mb-2">
                Password
              </label>
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent"
                placeholder="Enter your password"
              />
            </div>

            {error && (
              <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">
                {error}
              </div>
            )}

            <button
              type="submit"
              className="w-full bg-emerald-600 hover:bg-emerald-700 text-white py-3 rounded-lg transition-colors"
            >
              Login
            </button>
          </form>

          {/* Access Instructions */}
          <div className="mt-6 p-4 bg-emerald-50 rounded-lg">
            <p className="text-xs text-emerald-800 mb-2">
              <strong>Access Instructions:</strong>
            </p>
            <p className="text-xs text-emerald-700">
              • Use an account created by a TechBin administrator
              <br />• Public self-registration is disabled
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
