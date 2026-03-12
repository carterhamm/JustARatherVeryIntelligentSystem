import { useState, FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '@/hooks/useAuth';
import { Eye, EyeOff, Loader2 } from 'lucide-react';

export default function RegisterPage() {
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const { register } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');

    if (!username.trim() || !email.trim() || !password.trim() || !confirmPassword.trim()) {
      setError('Please fill in all fields.');
      return;
    }

    if (password !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }

    if (password.length < 8) {
      setError('Password must be at least 8 characters.');
      return;
    }

    setIsLoading(true);
    try {
      await register(email, username, password);
      navigate('/');
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'response' in err) {
        const axiosErr = err as { response?: { data?: { detail?: string; message?: string } } };
        setError(
          axiosErr.response?.data?.detail ||
          axiosErr.response?.data?.message ||
          'Registration failed. Please try again.'
        );
      } else {
        setError('Registration failed. Please try again.');
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="relative min-h-screen w-full flex items-center justify-center bg-jarvis-darker overflow-hidden">
      {/* Animated background grid */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div
          className="absolute inset-0 opacity-[0.07]"
          style={{
            backgroundImage:
              'linear-gradient(rgba(0, 212, 255, 0.4) 1px, transparent 1px), linear-gradient(90deg, rgba(0, 212, 255, 0.4) 1px, transparent 1px)',
            backgroundSize: '60px 60px',
            animation: 'gridDrift 20s linear infinite',
          }}
        />
        <div
          className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[800px] rounded-full"
          style={{
            background:
              'radial-gradient(circle, rgba(0, 212, 255, 0.08) 0%, rgba(0, 128, 255, 0.04) 40%, transparent 70%)',
          }}
        />
        {Array.from({ length: 20 }).map((_, i) => (
          <div
            key={i}
            className="absolute w-1 h-1 rounded-full bg-jarvis-blue/30"
            style={{
              left: `${Math.random() * 100}%`,
              top: `${Math.random() * 100}%`,
              animation: `floatParticle ${8 + Math.random() * 12}s ease-in-out infinite`,
              animationDelay: `${Math.random() * 5}s`,
            }}
          />
        ))}
      </div>

      {/* Register Card */}
      <div className="relative z-10 w-full max-w-md mx-4">
        <div className="glass-panel hud-clip-md p-8 shadow-jarvis-lg">
          {/* JARVIS Branding */}
          <div className="text-center mb-8">
            <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-gradient-to-br from-jarvis-blue/20 to-jarvis-cyan/10 border border-jarvis-blue/30 mb-4">
              <span className="text-2xl font-display font-bold text-jarvis-blue glow-text">J</span>
            </div>
            <h1 className="text-2xl font-display font-bold tracking-widest text-jarvis-blue glow-text">
              J.A.R.V.I.S.
            </h1>
            <p className="text-sm text-gray-400 mt-1 tracking-wide">
              Create Your Account
            </p>
          </div>

          {/* Error Display */}
          {error && (
            <div className="mb-6 px-4 py-3 hud-clip-sm bg-red-500/10 border border-red-500/30 text-red-400 text-sm text-center">
              {error}
            </div>
          )}

          {/* Register Form */}
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="username" className="block text-xs font-medium text-jarvis-blue/70 mb-1.5 tracking-wider uppercase">
                Username
              </label>
              <input
                id="username"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="tonystark"
                className="w-full jarvis-input hud-clip-sm px-4 py-3 text-sm"
                autoComplete="username"
                autoFocus
                disabled={isLoading}
              />
            </div>

            <div>
              <label htmlFor="email" className="block text-xs font-medium text-jarvis-blue/70 mb-1.5 tracking-wider uppercase">
                Email
              </label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="stark@avengers.com"
                className="w-full jarvis-input hud-clip-sm px-4 py-3 text-sm"
                autoComplete="email"
                disabled={isLoading}
              />
            </div>

            <div>
              <label htmlFor="password" className="block text-xs font-medium text-jarvis-blue/70 mb-1.5 tracking-wider uppercase">
                Password
              </label>
              <div className="relative">
                <input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Min. 8 characters"
                  className="w-full jarvis-input hud-clip-sm px-4 py-3 pr-11 text-sm"
                  autoComplete="new-password"
                  disabled={isLoading}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-jarvis-blue transition-colors"
                  tabIndex={-1}
                >
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            <div>
              <label htmlFor="confirm-password" className="block text-xs font-medium text-jarvis-blue/70 mb-1.5 tracking-wider uppercase">
                Confirm Password
              </label>
              <input
                id="confirm-password"
                type={showPassword ? 'text' : 'password'}
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="Repeat your password"
                className="w-full jarvis-input hud-clip-sm px-4 py-3 text-sm"
                autoComplete="new-password"
                disabled={isLoading}
              />
            </div>

            <button
              type="submit"
              disabled={isLoading}
              className="w-full jarvis-button jarvis-button-gold hud-clip-sm py-3 text-sm font-semibold tracking-wider uppercase flex items-center justify-center gap-2 mt-2"
            >
              {isLoading ? (
                <>
                  <Loader2 size={16} className="animate-spin" />
                  Creating Account...
                </>
              ) : (
                'Register'
              )}
            </button>
          </form>

          {/* Login Link */}
          <div className="mt-6 text-center">
            <span className="text-sm text-gray-500">Already have an account? </span>
            <Link
              to="/login"
              className="text-sm text-jarvis-blue hover:text-jarvis-cyan transition-colors underline underline-offset-2"
            >
              Sign in
            </Link>
          </div>
        </div>

        {/* Footer */}
        <div className="text-center mt-6 text-[11px] text-gray-600">
          Stark Industries -- Secure Access Portal
        </div>
      </div>

      {/* Inline animation keyframes */}
      <style>{`
        @keyframes floatParticle {
          0%, 100% { transform: translateY(0) translateX(0); opacity: 0.3; }
          25% { transform: translateY(-20px) translateX(10px); opacity: 0.6; }
          50% { transform: translateY(-10px) translateX(-10px); opacity: 0.3; }
          75% { transform: translateY(-30px) translateX(5px); opacity: 0.5; }
        }
        @keyframes gridDrift {
          0% { transform: translate(0, 0); }
          100% { transform: translate(60px, 60px); }
        }
      `}</style>
    </div>
  );
}
