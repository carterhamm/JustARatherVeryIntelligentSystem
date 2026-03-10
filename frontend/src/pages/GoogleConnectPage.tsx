import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '@/stores/authStore';
import { Loader2, Shield } from 'lucide-react';

/**
 * /connect/google — Public landing page for Google OAuth.
 *
 * If logged in: fetches the Google auth URL and redirects to Google consent.
 * If not logged in: stores intent in localStorage, redirects to /login.
 * After login, AuthPage checks for the stored intent and bounces back here.
 */
export default function GoogleConnectPage() {
  const token = useAuthStore((s) => s.token);
  const navigate = useNavigate();
  const [error, setError] = useState('');

  useEffect(() => {
    if (!token) {
      // Not logged in — store redirect intent and go to login
      localStorage.setItem('jarvis_post_login_redirect', '/connect/google');
      navigate('/login', { replace: true });
      return;
    }

    // Logged in — fetch the auth URL and redirect to Google
    const fetchAndRedirect = async () => {
      try {
        const resp = await fetch('/api/v1/google/auth-url', {
          headers: { Authorization: `Bearer ${token}` },
        });

        if (resp.status === 401) {
          // Token expired — send to login
          localStorage.setItem('jarvis_post_login_redirect', '/connect/google');
          navigate('/login', { replace: true });
          return;
        }

        if (!resp.ok) {
          const data = await resp.json().catch(() => ({}));
          setError(data.detail || `Error ${resp.status}`);
          return;
        }

        const data = await resp.json();
        if (data.auth_url) {
          window.location.href = data.auth_url;
        } else {
          setError('No auth URL returned from server.');
        }
      } catch (err) {
        setError('Failed to connect to JARVIS. Please try again.');
      }
    };

    fetchAndRedirect();
  }, [token, navigate]);

  return (
    <div className="min-h-screen w-full flex items-center justify-center bg-black">
      <div className="text-center max-w-md mx-5">
        <div className="inline-flex items-center justify-center w-14 h-14 mb-4 rounded-2xl bg-gradient-to-br from-jarvis-blue/15 to-blue-500/10 border border-jarvis-blue/10">
          <Shield size={24} className="text-jarvis-blue" />
        </div>

        {error ? (
          <>
            <h1 className="text-lg font-display font-bold text-red-400 mb-2">Connection Error</h1>
            <p className="text-sm text-gray-400 mb-4">{error}</p>
            <button
              onClick={() => window.location.reload()}
              className="jarvis-button px-6 py-2 text-sm"
            >
              Try Again
            </button>
          </>
        ) : (
          <>
            <h1 className="text-lg font-display font-bold text-jarvis-blue mb-2">
              Connecting to Google
            </h1>
            <p className="text-sm text-gray-400 mb-4">Redirecting to Google sign-in...</p>
            <Loader2 size={24} className="animate-spin text-jarvis-blue mx-auto" />
          </>
        )}
      </div>
    </div>
  );
}
