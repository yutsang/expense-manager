"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useAuthStore } from "@/lib/auth-store";

const signupSchema = z.object({
  display_name: z.string().min(1, "Name is required"),
  email: z.string().email("Enter a valid email address"),
  password: z.string().min(8, "Password must be at least 8 characters"),
  tenant_name: z.string().min(1, "Company name is required"),
  country: z.string().min(2),
  currency: z.string().min(3),
});

type SignupForm = z.infer<typeof signupSchema>;

export default function SignupPage() {
  const router = useRouter();
  const { setUser } = useAuthStore();
  const [serverError, setServerError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<SignupForm>({
    resolver: zodResolver(signupSchema),
    defaultValues: { country: "US" as string, currency: "USD" as string },
  });

  const onSubmit = async (data: SignupForm) => {
    setServerError(null);
    try {
      const res = await fetch("/v1/auth/signup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
        credentials: "include",
      });
      if (!res.ok) {
        const detail = (await res.json().catch(() => ({}))) as { detail?: string };
        throw new Error(detail.detail ?? "Signup failed");
      }
      const result = (await res.json()) as {
        access_token?: string;
        user: { id: string; email: string; display_name: string; current_tenant_id: string | null };
        tenant_id?: string;
        tenant_ids?: string[];
      };
      if (typeof window !== "undefined") {
        if (result.access_token) localStorage.setItem("aegis_token", result.access_token);
        const tid = result.tenant_id ?? result.tenant_ids?.[0];
        if (tid) localStorage.setItem("aegis_tenant_id", tid);
        document.cookie = "aegis_client=1; path=/; max-age=86400; SameSite=Lax";
      }
      setUser(result.user);
      router.push("/dashboard");
    } catch (err: unknown) {
      setServerError(err instanceof Error ? err.message : "Signup failed");
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4">
      <div className="w-full max-w-sm space-y-6">
        <div className="text-center">
          <h1 className="text-2xl font-bold tracking-tight">Aegis ERP</h1>
          <p className="mt-1 text-sm text-muted-foreground">Create your account</p>
        </div>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
          <div className="space-y-1">
            <label htmlFor="display_name" className="text-sm font-medium">Full name</label>
            <input
              id="display_name"
              type="text"
              autoComplete="name"
              {...register("display_name")}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
              placeholder="Jane Smith"
            />
            {errors.display_name && <p className="text-xs text-destructive">{errors.display_name.message}</p>}
          </div>

          <div className="space-y-1">
            <label htmlFor="email" className="text-sm font-medium">Work email</label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              {...register("email")}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
              placeholder="jane@company.com"
            />
            {errors.email && <p className="text-xs text-destructive">{errors.email.message}</p>}
          </div>

          <div className="space-y-1">
            <label htmlFor="password" className="text-sm font-medium">Password</label>
            <input
              id="password"
              type="password"
              autoComplete="new-password"
              {...register("password")}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
              placeholder="Min. 8 characters"
            />
            {errors.password && <p className="text-xs text-destructive">{errors.password.message}</p>}
          </div>

          <div className="space-y-1">
            <label htmlFor="tenant_name" className="text-sm font-medium">Company name</label>
            <input
              id="tenant_name"
              type="text"
              autoComplete="organization"
              {...register("tenant_name")}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
              placeholder="Acme Corp"
            />
            {errors.tenant_name && <p className="text-xs text-destructive">{errors.tenant_name.message}</p>}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label htmlFor="country" className="text-sm font-medium">Country</label>
              <select
                id="country"
                {...register("country")}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
              >
                <option value="US">United States</option>
                <option value="AU">Australia</option>
                <option value="GB">United Kingdom</option>
                <option value="HK">Hong Kong</option>
                <option value="SG">Singapore</option>
              </select>
            </div>
            <div className="space-y-1">
              <label htmlFor="currency" className="text-sm font-medium">Currency</label>
              <select
                id="currency"
                {...register("currency")}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
              >
                <option value="USD">USD</option>
                <option value="AUD">AUD</option>
                <option value="GBP">GBP</option>
                <option value="HKD">HKD</option>
                <option value="SGD">SGD</option>
              </select>
            </div>
          </div>

          {serverError && (
            <div className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {serverError}
            </div>
          )}

          <button
            type="submit"
            disabled={isSubmitting}
            className="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isSubmitting ? "Creating account…" : "Create account"}
          </button>
        </form>

        <p className="text-center text-xs text-muted-foreground">
          Already have an account?{" "}
          <a href="/login" className="underline underline-offset-2 hover:text-foreground">
            Sign in
          </a>
        </p>
      </div>
    </div>
  );
}
