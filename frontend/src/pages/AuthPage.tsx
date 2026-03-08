import { useState, FormEvent, useMemo, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/hooks/useAuth';
import { isWebAuthnAvailable } from '@/utils/webauthn';
import { Loader2, Shield, Fingerprint, User, Mail, ArrowRight, AlertTriangle, Check, Key } from 'lucide-react';
import gsap from 'gsap';
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
  const [setupToken, setSetupToken] = useState('');
  const [shtVerified, setShtVerified] = useState(false);
  const [shtChecking, setShtChecking] = useState(false);

  const { lookup, passkeyRegister, passkeyLogin } = useAuth();
  const navigate = useNavigate();

  const webauthnSupported = useMemo(() => isWebAuthnAvailable(), []);
  const containerRef = useRef<HTMLDivElement>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const headerRef = useRef<HTMLDivElement>(null);
  const footerRef = useRef<HTMLDivElement>(null);

  // GSAP boot-up sequence
  useEffect(() => {
    const tl = gsap.timeline();

    if (headerRef.current) {
      tl.fromTo(
        headerRef.current,
        { opacity: 0, y: -10 },
        { opacity: 1, y: 0, duration: 0.5, ease: 'power3.out' },
        0.2,
      );
    }

    if (cardRef.current) {
      tl.fromTo(
        cardRef.current,
        { opacity: 0, scale: 0.95, y: 15 },
        { opacity: 1, scale: 1, y: 0, duration: 0.6, ease: 'power3.out' },
        0.35,
      );
    }

    if (footerRef.current) {
      tl.fromTo(
        footerRef.current,
        { opacity: 0, y: 10 },
        { opacity: 1, y: 0, duration: 0.4, ease: 'power3.out' },
        0.55,
      );
    }
  }, []);

  // Particles
  const particles = useMemo(
    () =>
      Array.from({ length: 40 }, (_, i) => ({
        id: i,
        left: `${(i * 17 + 3) % 100}%`,
        top: `${(i * 23 + 7) % 100}%`,
        size: 1 + (i % 3),
        duration: `${8 + (i % 12)}s`,
        delay: `${(i * 0.4) % 5}s`,
      })),
    [],
  );

  const stepIndex = step === 'identify' ? 0 : 1;

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
        if (trimmed.includes('@')) setEmail(trimmed);
        else setUsername(trimmed);
        setStep('register');
      }
    } catch {
      setError('Connection error. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

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
      await passkeyRegister(emailVal, usernameVal, fullName || undefined, setupToken.trim());
      navigate('/');
    } catch (err: any) {
      const detail = err?.response?.data?.detail || err?.message || 'Registration failed.';
      setError(detail);
    } finally {
      setIsLoading(false);
    }
  };

  const handleVerifySht = async () => {
    setShtChecking(true);
    setError('');
    try {
      // Use the register endpoint's x-setup-token header pattern to verify
      const resp = await fetch(
        `${import.meta.env.VITE_API_URL || ''}/api/v1/auth/verify-setup-token`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ setup_token: setupToken.trim() }),
        }
      );
      if (resp.ok) {
        setShtVerified(true);
      } else {
        setError('Invalid System Handshake Token.');
        setShtVerified(false);
      }
    } catch {
      setError('Could not verify token. Please try again.');
      setShtVerified(false);
    } finally {
      setShtChecking(false);
    }
  };

  return (
    <div ref={containerRef} className="relative min-h-screen w-full flex items-center justify-center bg-black overflow-hidden">
      {/* Background */}
      <div className="absolute inset-0 pointer-events-none">
        {/* Grid */}
        <div
          className="absolute inset-0 opacity-[0.03]"
          style={{
            backgroundImage:
              'linear-gradient(rgba(0, 212, 255, 0.5) 1px, transparent 1px), linear-gradient(90deg, rgba(0, 212, 255, 0.5) 1px, transparent 1px)',
            backgroundSize: '60px 60px',
            animation: 'gridDrift 20s linear infinite',
          }}
        />
        {/* Radial glow */}
        <div
          className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[800px] rounded-full"
          style={{
            background:
              'radial-gradient(circle, rgba(0, 212, 255, 0.06) 0%, rgba(0, 128, 255, 0.03) 40%, transparent 70%)',
          }}
        />
        {/* Particles */}
        {particles.map((p) => (
          <div
            key={p.id}
            className="absolute rounded-full bg-jarvis-blue/20"
            style={{
              left: p.left,
              top: p.top,
              width: `${p.size}px`,
              height: `${p.size}px`,
              animation: `floatParticle ${p.duration} ease-in-out infinite`,
              animationDelay: p.delay,
            }}
          />
        ))}
      </div>


      {/* Corner brackets */}
      {(['tl', 'tr', 'bl', 'br'] as const).map((pos) => {
        const isTop = pos.startsWith('t');
        const isLeft = pos.endsWith('l');
        return (
          <div
            key={pos}
            className="absolute pointer-events-none z-10"
            style={{ [isTop ? 'top' : 'bottom']: '16px', [isLeft ? 'left' : 'right']: '16px' }}
          >
            <svg width="40" height="40" viewBox="0 0 40 40" fill="none">
              <path
                d={
                  isTop && isLeft
                    ? 'M0 16 L0 0 L16 0'
                    : isTop && !isLeft
                      ? 'M24 0 L40 0 L40 16'
                      : !isTop && isLeft
                        ? 'M0 24 L0 40 L16 40'
                        : 'M24 40 L40 40 L40 24'
                }
                stroke="rgba(0, 212, 255, 0.15)"
                strokeWidth="1"
              />
            </svg>
          </div>
        );
      })}

      {/* Auth Card */}
      <div className="relative z-10 w-full max-w-md mx-5">
        {/* Header label */}
        <div ref={headerRef} className="text-center mb-5 opacity-0">
          <span className="hud-label text-[10px]">STARK INDUSTRIES — SECURE ACCESS TERMINAL</span>
        </div>

        {/* Main panel */}
        <div ref={cardRef} className="glass-heavy rounded-3xl p-8 opacity-0">
          {/* Branding */}
          <div className="text-center mb-6">
            <div className="inline-flex items-center justify-center w-14 h-14 mb-3 rounded-2xl bg-gradient-to-br from-jarvis-blue/15 to-blue-500/10 border border-jarvis-blue/10">
              <Shield size={24} className="text-jarvis-blue" />
            </div>
            <h1 className="text-xl font-display font-bold tracking-[0.2em] text-jarvis-blue glow-text">
              J.A.R.V.I.S.
            </h1>
            <p className="text-[11px] text-gray-500 mt-1 tracking-wider font-mono">
              AUTHENTICATION PROTOCOL v2.0
            </p>
          </div>

          {/* Progress */}
          <div className="flex items-center gap-2 mb-6 px-4">
            <div
              className={clsx('h-0.5 flex-1 rounded-full transition-all duration-500', {
                'bg-jarvis-blue': stepIndex >= 0,
                'bg-gray-800': stepIndex < 0,
              })}
            />
            <div
              className={clsx('w-1.5 h-1.5 rounded-full transition-all duration-500', {
                'bg-jarvis-blue shadow-[0_0_6px_rgba(0,212,255,0.5)]': stepIndex >= 0,
                'bg-gray-800': stepIndex < 0,
              })}
            />
            <div
              className={clsx('h-0.5 flex-1 rounded-full transition-all duration-500', {
                'bg-jarvis-blue': stepIndex >= 1,
                'bg-gray-800': stepIndex < 1,
              })}
            />
            <div
              className={clsx('w-1.5 h-1.5 rounded-full transition-all duration-500', {
                'bg-jarvis-blue shadow-[0_0_6px_rgba(0,212,255,0.5)]': stepIndex >= 1,
                'bg-gray-800': stepIndex < 1,
              })}
            />
            <div
              className={clsx('h-0.5 flex-1 rounded-full transition-all duration-500', {
                'bg-jarvis-blue': step !== 'identify',
                'bg-gray-800': step === 'identify',
              })}
            />
          </div>

          {/* WebAuthn warning */}
          {!webauthnSupported && (
            <div className="mb-4 px-4 py-2.5 rounded-xl bg-hud-amber/10 border border-hud-amber/20 flex items-center gap-2">
              <AlertTriangle size={14} className="text-hud-amber flex-shrink-0" />
              <span className="text-xs text-hud-amber">Passkeys not supported in this browser.</span>
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="mb-4 px-4 py-2.5 rounded-xl bg-hud-red/10 border border-hud-red/20 text-hud-red text-xs text-center">
              {error}
            </div>
          )}

          {/* Step: Identify */}
          {step === 'identify' && (
            <form onSubmit={handleIdentify} className="space-y-4">
              <div>
                <label className="hud-label block mb-2">IDENTIFICATION</label>
                <div className="relative">
                  <Mail
                    size={14}
                    className="absolute left-4 top-1/2 -translate-y-1/2 text-jarvis-blue/40"
                  />
                  <input
                    type="text"
                    value={identifier}
                    onChange={(e) => setIdentifier(e.target.value)}
                    placeholder="Email or username"
                    className="w-full jarvis-input pl-10 pr-4 py-3 text-sm font-mono"
                    autoComplete="username webauthn"
                    autoFocus
                    disabled={isLoading}
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={isLoading || !identifier.trim()}
                className="jarvis-button-gold w-full py-3 text-sm font-display font-semibold tracking-wider uppercase flex items-center justify-center gap-2"
                style={{ opacity: isLoading || !identifier.trim() ? 0.4 : 1 }}
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

          {/* Step: Authenticate */}
          {step === 'authenticate' && (
            <div className="space-y-4">
              <div className="text-center">
                <div className="inline-flex items-center justify-center w-12 h-12 rounded-full glass-cyan mb-3">
                  <Fingerprint size={24} className="text-jarvis-blue" />
                </div>
                <p className="text-sm text-gray-300">
                  Welcome back,{' '}
                  <span className="text-jarvis-gold font-semibold">{existingUsername}</span>
                </p>
                <p className="text-xs text-gray-500 mt-1">Authenticate with your passkey</p>
              </div>

              <button
                onClick={handleAuthenticate}
                disabled={isLoading}
                className="jarvis-button w-full py-3 text-sm font-display font-semibold tracking-wider uppercase flex items-center justify-center gap-2"
                style={{ opacity: isLoading ? 0.5 : 1 }}
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
                onClick={() => {
                  setStep('identify');
                  setError('');
                }}
                className="w-full text-center text-xs text-gray-500 hover:text-gray-300 transition-colors mt-2"
              >
                Use a different account
              </button>
            </div>
          )}

          {/* Step: Register */}
          {step === 'register' && (
            <form onSubmit={handleRegister} className="space-y-3">
              <div className="text-center mb-2">
                <p className="text-xs text-gray-400">New user detected. Complete your profile.</p>
              </div>

              <div>
                <label className="hud-label block mb-1.5">EMAIL</label>
                <div className="relative">
                  <Mail
                    size={14}
                    className="absolute left-4 top-1/2 -translate-y-1/2 text-jarvis-blue/40"
                  />
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="stark@avengers.com"
                    className="w-full jarvis-input pl-10 pr-4 py-2.5 text-sm font-mono"
                    autoComplete="email"
                    disabled={isLoading}
                  />
                </div>
              </div>

              <div>
                <label className="hud-label block mb-1.5">USERNAME</label>
                <div className="relative">
                  <User
                    size={14}
                    className="absolute left-4 top-1/2 -translate-y-1/2 text-jarvis-blue/40"
                  />
                  <input
                    type="text"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    placeholder="tonystark"
                    className="w-full jarvis-input pl-10 pr-4 py-2.5 text-sm font-mono"
                    autoComplete="username"
                    disabled={isLoading}
                  />
                </div>
              </div>

              <div>
                <label className="hud-label block mb-1.5">
                  DISPLAY NAME <span className="text-gray-600">(OPTIONAL)</span>
                </label>
                <input
                  type="text"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  placeholder="Tony Stark"
                  className="w-full jarvis-input px-4 py-2.5 text-sm"
                  disabled={isLoading}
                />
              </div>

              <div>
                <label className="hud-label block mb-1.5">
                  SYSTEM HANDSHAKE TOKEN
                </label>
                <div className="flex gap-2">
                  <div className="relative flex-1">
                    <Key
                      size={14}
                      className="absolute left-4 top-1/2 -translate-y-1/2 text-jarvis-blue/40"
                    />
                    <input
                      type="password"
                      value={setupToken}
                      onChange={(e) => { setSetupToken(e.target.value); setShtVerified(false); }}
                      placeholder="Enter SHT"
                      className="w-full jarvis-input pl-10 pr-4 py-2.5 text-sm font-mono"
                      disabled={isLoading || shtVerified}
                    />
                  </div>
                  <button
                    type="button"
                    onClick={handleVerifySht}
                    disabled={!setupToken.trim() || shtChecking || shtVerified}
                    className={clsx(
                      'w-11 h-11 flex items-center justify-center rounded-xl border transition-all flex-shrink-0',
                      shtVerified
                        ? 'bg-hud-green/15 border-hud-green/30'
                        : 'glass-subtle border-white/[0.06] hover:border-jarvis-blue/20',
                      (!setupToken.trim() || shtChecking) && !shtVerified && 'opacity-40'
                    )}
                  >
                    {shtChecking ? (
                      <Loader2 size={14} className="animate-spin text-jarvis-blue" />
                    ) : shtVerified ? (
                      <Check size={14} className="text-hud-green" />
                    ) : (
                      <ArrowRight size={14} className="text-jarvis-blue" />
                    )}
                  </button>
                </div>
              </div>

              <button
                type="submit"
                disabled={isLoading || !email.trim() || !username.trim() || !shtVerified}
                className="jarvis-button-gold w-full py-3 text-sm font-display font-semibold tracking-wider uppercase flex items-center justify-center gap-2 mt-2"
                style={{
                  opacity: isLoading || !email.trim() || !username.trim() || !shtVerified ? 0.4 : 1,
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
                onClick={() => {
                  setStep('identify');
                  setError('');
                }}
                className="w-full text-center text-xs text-gray-500 hover:text-gray-300 transition-colors"
              >
                Back
              </button>
            </form>
          )}
        </div>

        {/* Footer */}
        <div ref={footerRef} className="text-center mt-4 opacity-0">
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
