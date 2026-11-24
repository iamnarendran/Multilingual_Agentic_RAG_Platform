"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Spinner, Wordmark } from "@/components/brand";
import { ScriptStack } from "@/components/script-stack";
import { useAuth } from "@/lib/auth";

export function AuthScreen({ mode }: { mode: "login" | "register" }) {
  const { user, ready, login, register } = useAuth();
  const router = useRouter();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (ready && user) router.replace("/");
  }, [ready, user, router]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (mode === "login") await login(email, password);
      else await register(name, email, password);
      router.replace("/");
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  const isLogin = mode === "login";
  const field =
    "w-full rounded-[10px] border border-line bg-raised px-3.5 py-2.5 text-[0.98rem] text-ink placeholder:text-ink-faint focus:border-indigo focus:outline-none focus:ring-2 focus:ring-ring/25";

  return (
    <main className="grid min-h-dvh lg:grid-cols-[1.15fr_1fr]">
      <section className="hidden flex-col justify-between bg-sidebar px-14 py-12 lg:flex">
        <Wordmark />
        <ScriptStack />
        <p className="max-w-[44ch] text-ink-soft">
          Upload documents in English or any of 22 Indian languages. Ask in the language you think in, and every answer
          points to the page it came from.
        </p>
      </section>

      <section className="flex items-center justify-center px-5 py-12">
        <div className="w-full max-w-[22rem]">
          <Wordmark className="mb-10 lg:hidden" />
          <h1 className="text-[1.75rem] font-[650] leading-tight" style={{ fontStretch: "105%" }}>
            {isLogin ? "Sign in" : "Create your account"}
          </h1>
          <p className="mt-1.5 text-ink-soft">
            {isLogin ? "Pick up where your documents left off." : "Your documents stay private to your account."}
          </p>

          <form onSubmit={submit} className="mt-8 space-y-4" noValidate>
            {!isLogin && (
              <label className="block">
                <span className="mb-1.5 block text-sm font-medium">Name</span>
                <input className={field} value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" required />
              </label>
            )}
            <label className="block">
              <span className="mb-1.5 block text-sm font-medium">Email</span>
              <input
                className={field}
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
                required
              />
            </label>
            <label className="block">
              <span className="mb-1.5 block text-sm font-medium">Password</span>
              <input
                className={field}
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete={isLogin ? "current-password" : "new-password"}
                minLength={isLogin ? undefined : 8}
                required
              />
              {!isLogin && <span className="mt-1.5 block text-sm text-ink-faint">At least 8 characters.</span>}
            </label>

            {error && (
              <p role="alert" className="rounded-[10px] bg-rose-wash px-3.5 py-2.5 text-sm text-rose">
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={busy}
              className="flex w-full items-center justify-center gap-2 rounded-[10px] bg-indigo px-4 py-2.5 font-semibold text-on-indigo transition-colors hover:bg-indigo-strong disabled:opacity-70"
            >
              {busy && <Spinner />}
              {isLogin ? "Sign in" : "Create account"}
            </button>
          </form>

          <p className="mt-6 text-sm text-ink-soft">
            {isLogin ? "New here? " : "Already have an account? "}
            <Link href={isLogin ? "/register" : "/login"} className="font-semibold text-indigo hover:underline">
              {isLogin ? "Create an account" : "Sign in"}
            </Link>
          </p>
        </div>
      </section>
    </main>
  );
}
