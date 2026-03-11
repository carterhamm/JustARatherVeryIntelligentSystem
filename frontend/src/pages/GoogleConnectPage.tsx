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
    <div className="min-h-screen w-full flex items-center justify-center" style={{ background: '#0A0E17' }}>
      <div className="text-center max-w-sm mx-5 px-10 py-12 border border-jarvis-blue/15"
        style={{
          background: 'rgba(8, 14, 30, 0.9)',
          clipPath: 'polygon(0 10px, 10px 0, calc(100% - 10px) 0, 100% 10px, 100% calc(100% - 10px), calc(100% - 10px) 100%, 10px 100%, 0 calc(100% - 10px))',
        }}>
        <div className="w-12 h-12 mx-auto mb-5 flex items-center justify-center"
          style={{
            clipPath: 'polygon(50% 0%, 100% 25%, 100% 75%, 50% 100%, 0% 75%, 0% 25%)',
            background: error
              ? 'linear-gradient(135deg, rgba(255, 68, 68, 0.25), rgba(255, 100, 100, 0.1))'
              : 'linear-gradient(135deg, rgba(0, 212, 255, 0.25), rgba(0, 128, 255, 0.15))',
          }}>
          {error
            ? <Shield size={20} className="text-red-400" />
            : <Shield size={20} className="text-jarvis-blue" />
          }
        </div>

        <span className="hud-label text-[8px] block mb-3">
          {error ? 'LINK FAILED' : 'ESTABLISHING LINK'}
        </span>

        {error ? (
          <>
            <h1 className="text-sm font-display font-bold text-red-400 tracking-widest mb-2">
              CONNECTION ERROR
            </h1>
            <p className="text-[11px] text-gray-500 font-mono mb-4">{error}</p>
            <button
              onClick={() => window.location.reload()}
              className="jarvis-button px-6 py-2 text-[11px] font-mono tracking-wider"
            >
              RETRY
            </button>
          </>
        ) : (
          <>
            <h1 className="text-sm font-display font-bold text-jarvis-blue tracking-widest mb-2">
              GOOGLE OAUTH
            </h1>
            <p className="text-[11px] text-gray-500 font-mono mb-5">Redirecting to Google sign-in...</p>
            <Loader2 size={18} className="animate-spin text-jarvis-blue mx-auto" />
          </>
        )}

        <div className="w-16 h-px mx-auto mt-5"
          style={{ background: 'linear-gradient(90deg, transparent, rgba(0, 212, 255, 0.2), transparent)' }} />
      </div>
    </div>
  );
}
