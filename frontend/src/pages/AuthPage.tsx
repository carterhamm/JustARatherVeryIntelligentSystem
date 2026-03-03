import { useState, FormEvent, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/hooks/useAuth';
import { isWebAuthnAvailable } from '@/utils/webauthn';
import { Loader2, Shield, Fingerprint, User, Mail, ArrowRight, AlertTriangle } from 'lucide-react';
import clsx from 'clsx';

type AuthStep = 'identify' | 'authenticate' | 'register';

export default function AuthPage() {
  const [step, setStep] = useState<AuthStep>('identify');
  const [identifier, setIdentifier] = useState('');
  const [username, setUsername] = useState('');
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [existingUsername, setExistingUsername] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const { lookup, passkeyRegister, passkeyLogin } = useAuth();
  const navigate = useNavigate();

  const webauthnSupported = useMemo(() => isWebAuthnAvailable(), []);

  // Particles for background — stable across renders
  const particles = useMemo(
    () =>
      Array.from({ length: 30 }, (_, i) => ({
        id: i,
        left: `${(i * 17 + 3) % 100}%`,
        top: `${(i * 23 + 7) % 100}%`,
        duration: `${8 + (i % 12)}s`,
        delay: `${(i * 0.4) % 5}s`,
      })),
    [],
  );

  const stepIndex = step === 'identify' ? 0 : step === 'authenticate' ? 1 : 1;

  // Handle identifier submission
  const handleIdentify = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    const trimmed = identifier.trim();
    if (!trimmed) {
      setError('Please enter your email or username.');
      return;
    }
    setIsLoading(true);
    try {
      const result = await lookup(trimmed);
      if (result.exists) {
        setExistingUsername(result.username || trimmed);
        setStep('authenticate');
      } else {
        // Pre-fill email if identifier looks like email
        if (trimmed.includes('@')) {
          setEmail(trimmed);
        } else {
          setUsername(trimmed);
        }
        setStep('register');
      }
    } catch {
      setError('Connection error. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  // Handle passkey authentication
  const handleAuthenticate = async () => {
    setError('');
    setIsLoading(true);
    try {
      await passkeyLogin(identifier.trim());
      navigate('/');
    } catch (err: any) {
      const detail = err?.response?.data?.detail || err?.message || 'Authentication failed.';
      setError(detail);
    } finally {
      setIsLoading(false);
    }
  };

  // Handle passkey registration
  const handleRegister = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    const emailVal = email.trim();
    const usernameVal = username.trim();

    if (!emailVal || !usernameVal) {
      setError('Email and username are required.');
      return;
    }
    if (!emailVal.includes('@')) {
      setError('Please enter a valid email.');
      return;
    }
    if (usernameVal.length < 3) {
      setError('Username must be at least 3 characters.');
      return;
    }

    setIsLoading(true);
    try {
      await passkeyRegister(emailVal, usernameVal, fullName || undefined);
      navigate('/');
    } catch (err: any) {
      const detail = err?.response?.data?.detail || err?.message || 'Registration failed.';
      setError(detail);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="relative min-h-screen w-full flex items-center justify-center bg-jarvis-darker overflow-hidden">
      {/* Background layers */}
      <div className="absolute inset-0 pointer-events-none">
        {/* Grid */}
        <div
          className="absolute inset-0 opacity-[0.04]"
          style={{
            backgroundImage:
              'linear-gradient(rgba(0, 212, 255, 0.5) 1px, transparent 1px), linear-gradient(90deg, rgba(0, 212, 255, 0.5) 1px, transparent 1px)',
            backgroundSize: '60px 60px',
            animation: 'gridDrift 20s linear infinite',
          }}
        />
        {/* Radial glow */}
        <div
          className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[900px] h-[900px] rounded-full"
          style={{
            background:
              'radial-gradient(circle, rgba(0, 212, 255, 0.06) 0%, rgba(0, 128, 255, 0.03) 40%, transparent 70%)',
          }}
        />
        {/* Particles */}
        {particles.map((p) => (
          <div
            key={p.id}
            className="absolute w-1 h-1 rounded-full bg-jarvis-blue/20"
            style={{
              left: p.left,
              top: p.top,
              animation: `floatParticle ${p.duration} ease-in-out infinite`,
              animationDelay: p.delay,
            }}
          />
        ))}
        {/* Scan lines */}
        <div className="absolute inset-0 opacity-[0.02]" style={{
          backgroundImage: 'repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0, 212, 255, 0.1) 2px, rgba(0, 212, 255, 0.1) 4px)',
        }} />
      </div>

      {/* Auth Card */}
      <div className="relative z-10 w-full max-w-md mx-4">
        {/* Top header label */}
        <div className="text-center mb-4 hud-boot-1">
          <span className="hud-label text-[10px]">STARK INDUSTRIES — SECURE ACCESS TERMINAL</span>
        </div>

        {/* Main panel */}
        <div className="hud-panel-lg p-8 hud-boot-2">
          {/* Branding */}
          <div className="text-center mb-6">
            <div className="inline-flex items-center justify-center w-14 h-14 mb-3" style={{
              clipPath: 'polygon(50% 0%, 100% 25%, 100% 75%, 50% 100%, 0% 75%, 0% 25%)',
              background: 'linear-gradient(135deg, rgba(0, 212, 255, 0.15), rgba(0, 128, 255, 0.1))',
              border: '1px solid rgba(0, 212, 255, 0.3)',
            }}>
              <Shield size={24} className="text-jarvis-blue" />
            </div>
            <h1 className="text-xl font-display font-bold tracking-[0.2em] text-jarvis-blue glow-text">
              J.A.R.V.I.S.
            </h1>
            <p className="text-[11px] text-gray-500 mt-1 tracking-wider font-mono">
              AUTHENTICATION PROTOCOL v2.0
            </p>
          </div>

          {/* Step progress bar */}
          <div className="flex items-center gap-2 mb-6 px-4">
            <div className={clsx('h-0.5 flex-1 rounded-full transition-all duration-500', {
              'bg-jarvis-blue': stepIndex >= 0,
              'bg-gray-700': stepIndex < 0,
            })} />
            <div className={clsx('w-1.5 h-1.5 rounded-full transition-all duration-500', {
              'bg-jarvis-blue shadow-[0_0_6px_rgba(0,212,255,0.5)]': stepIndex >= 0,
              'bg-gray-700': stepIndex < 0,
            })} />
            <div className={clsx('h-0.5 flex-1 rounded-full transition-all duration-500', {
              'bg-jarvis-blue': stepIndex >= 1,
              'bg-gray-700': stepIndex < 1,
            })} />
            <div className={clsx('w-1.5 h-1.5 rounded-full transition-all duration-500', {
              'bg-jarvis-blue shadow-[0_0_6px_rgba(0,212,255,0.5)]': stepIndex >= 1,
              'bg-gray-700': stepIndex < 1,
            })} />
            <div className={clsx('h-0.5 flex-1 rounded-full transition-all duration-500', {
              'bg-jarvis-blue': step === 'register' || step === 'authenticate',
              'bg-gray-700': step === 'identify',
            })} />
          </div>

          {/* WebAuthn warning */}
          {!webauthnSupported && (
            <div className="mb-4 px-3 py-2 rounded bg-hud-amber/10 border border-hud-amber/30 flex items-center gap-2">
              <AlertTriangle size={14} className="text-hud-amber flex-shrink-0" />
              <span className="text-xs text-hud-amber">Passkeys not supported in this browser.</span>
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="mb-4 px-3 py-2 bg-hud-red/10 border border-hud-red/30 text-hud-red text-xs text-center"
              style={{ clipPath: 'polygon(0 4px, 4px 0, calc(100% - 4px) 0, 100% 4px, 100% calc(100% - 4px), calc(100% - 4px) 100%, 4px 100%, 0 calc(100% - 4px))' }}>
              {error}
            </div>
          )}

          {/* ─── Step: Identify ──────────────────────────────── */}
          {step === 'identify' && (
            <form onSubmit={handleIdentify} className="space-y-4">
              <div>
                <label className="hud-label block mb-2">IDENTIFICATION</label>
                <div className="relative">
                  <Mail size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-jarvis-blue/40" />
                  <input
                    type="text"
                    value={identifier}
                    onChange={(e) => setIdentifier(e.target.value)}
                    placeholder="Email or username"
                    className="w-full jarvis-input pl-9 pr-4 py-3 text-sm font-mono"
                    style={{ clipPath: 'polygon(0 4px, 4px 0, calc(100% - 4px) 0, 100% 4px, 100% calc(100% - 4px), calc(100% - 4px) 100%, 4px 100%, 0 calc(100% - 4px))' }}
                    autoComplete="username webauthn"
                    autoFocus
                    disabled={isLoading}
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={isLoading || !identifier.trim()}
                className="w-full py-3 text-sm font-display font-semibold tracking-wider uppercase flex items-center justify-center gap-2 transition-all"
                style={{
                  clipPath: 'polygon(0 4px, 4px 0, calc(100% - 4px) 0, 100% 4px, 100% calc(100% - 4px), calc(100% - 4px) 100%, 4px 100%, 0 calc(100% - 4px))',
                  background: 'linear-gradient(135deg, rgba(240, 165, 0, 0.2), rgba(200, 130, 0, 0.15))',
                  border: '1px solid rgba(240, 165, 0, 0.4)',
                  color: '#f0a500',
                  opacity: isLoading || !identifier.trim() ? 0.4 : 1,
                }}
              >
                {isLoading ? (
                  <Loader2 size={16} className="animate-spin" />
                ) : (
                  <>
                    Continue
                    <ArrowRight size={14} />
                  </>
                )}
              </button>
            </form>
          )}

          {/* ─── Step: Authenticate (returning user) ────────── */}
          {step === 'authenticate' && (
            <div className="space-y-4">
              <div className="text-center">
                <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-jarvis-blue/10 border border-jarvis-blue/20 mb-3">
                  <Fingerprint size={24} className="text-jarvis-blue" />
                </div>
                <p className="text-sm text-gray-300">
                  Welcome back, <span className="text-jarvis-gold font-semibold">{existingUsername}</span>
                </p>
                <p className="text-xs text-gray-500 mt-1">Authenticate with your passkey</p>
              </div>

              <button
                onClick={handleAuthenticate}
                disabled={isLoading}
                className="w-full py-3 text-sm font-display font-semibold tracking-wider uppercase flex items-center justify-center gap-2 transition-all"
                style={{
                  clipPath: 'polygon(0 4px, 4px 0, calc(100% - 4px) 0, 100% 4px, 100% calc(100% - 4px), calc(100% - 4px) 100%, 4px 100%, 0 calc(100% - 4px))',
                  background: 'linear-gradient(135deg, rgba(0, 212, 255, 0.2), rgba(0, 128, 255, 0.15))',
                  border: '1px solid rgba(0, 212, 255, 0.4)',
                  color: '#00d4ff',
                  opacity: isLoading ? 0.5 : 1,
                }}
              >
                {isLoading ? (
                  <Loader2 size={16} className="animate-spin" />
                ) : (
                  <>
                    <Fingerprint size={16} />
                    Verify Identity
                  </>
                )}
              </button>

              <button
                onClick={() => { setStep('identify'); setError(''); }}
                className="w-full text-center text-xs text-gray-500 hover:text-gray-300 transition-colors mt-2"
              >
                Use a different account
              </button>
            </div>
          )}

          {/* ─── Step: Register (new user) ──────────────────── */}
          {step === 'register' && (
            <form onSubmit={handleRegister} className="space-y-3">
              <div className="text-center mb-2">
                <p className="text-xs text-gray-400">New user detected. Complete your profile.</p>
              </div>

              <div>
                <label className="hud-label block mb-1.5">EMAIL</label>
                <div className="relative">
                  <Mail size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-jarvis-blue/40" />
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="stark@avengers.com"
                    className="w-full jarvis-input pl-9 pr-4 py-2.5 text-sm font-mono"
                    style={{ clipPath: 'polygon(0 4px, 4px 0, calc(100% - 4px) 0, 100% 4px, 100% calc(100% - 4px), calc(100% - 4px) 100%, 4px 100%, 0 calc(100% - 4px))' }}
                    autoComplete="email"
                    disabled={isLoading}
                  />
                </div>
              </div>

              <div>
                <label className="hud-label block mb-1.5">USERNAME</label>
                <div className="relative">
                  <User size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-jarvis-blue/40" />
                  <input
                    type="text"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    placeholder="tonystark"
                    className="w-full jarvis-input pl-9 pr-4 py-2.5 text-sm font-mono"
                    style={{ clipPath: 'polygon(0 4px, 4px 0, calc(100% - 4px) 0, 100% 4px, 100% calc(100% - 4px), calc(100% - 4px) 100%, 4px 100%, 0 calc(100% - 4px))' }}
                    autoComplete="username"
                    disabled={isLoading}
                  />
                </div>
              </div>

              <div>
                <label className="hud-label block mb-1.5">DISPLAY NAME <span className="text-gray-600">(OPTIONAL)</span></label>
                <input
                  type="text"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  placeholder="Tony Stark"
                  className="w-full jarvis-input px-4 py-2.5 text-sm"
                  style={{ clipPath: 'polygon(0 4px, 4px 0, calc(100% - 4px) 0, 100% 4px, 100% calc(100% - 4px), calc(100% - 4px) 100%, 4px 100%, 0 calc(100% - 4px))' }}
                  disabled={isLoading}
                />
              </div>

              <button
                type="submit"
                disabled={isLoading || !email.trim() || !username.trim()}
                className="w-full py-3 text-sm font-display font-semibold tracking-wider uppercase flex items-center justify-center gap-2 transition-all mt-2"
                style={{
                  clipPath: 'polygon(0 4px, 4px 0, calc(100% - 4px) 0, 100% 4px, 100% calc(100% - 4px), calc(100% - 4px) 100%, 4px 100%, 0 calc(100% - 4px))',
                  background: 'linear-gradient(135deg, rgba(240, 165, 0, 0.2), rgba(200, 130, 0, 0.15))',
                  border: '1px solid rgba(240, 165, 0, 0.4)',
                  color: '#f0a500',
                  opacity: isLoading || !email.trim() || !username.trim() ? 0.4 : 1,
                }}
              >
                {isLoading ? (
                  <Loader2 size={16} className="animate-spin" />
                ) : (
                  <>
                    <Fingerprint size={16} />
                    Create Passkey & Register
                  </>
                )}
              </button>

              <button
                type="button"
                onClick={() => { setStep('identify'); setError(''); }}
                className="w-full text-center text-xs text-gray-500 hover:text-gray-300 transition-colors"
              >
                Back
              </button>
            </form>
          )}
        </div>

        {/* Footer */}
        <div className="text-center mt-4 hud-boot-3">
          <div className="hud-divider mb-2">
            <div className="hud-divider-dot" />
          </div>
          <span className="hud-label text-[9px] text-gray-600">
            ENCRYPTED BIOMETRIC AUTHENTICATION
          </span>
        </div>
      </div>
    </div>
  );
}
