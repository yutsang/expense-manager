"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import {
  ArrowLeft,
  Building2,
  Globe,
  ShieldAlert,
  ShieldCheck,
  User,
} from "lucide-react";
import { sanctionsApi, type SanctionsEntry } from "@/lib/api";

const SOURCE_LABELS: Record<string, { label: string; short: string; color: string }> = {
  ofac_consolidated: {
    label: "OFAC Consolidated List",
    short: "OFAC",
    color: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
  },
  un_consolidated: {
    label: "UN Consolidated Sanctions List",
    short: "UN",
    color: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
  },
  uk_ofsi: {
    label: "UK OFSI Consolidated",
    short: "UK OFSI",
    color: "bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400",
  },
  eu_consolidated: {
    label: "EU Consolidated Sanctions",
    short: "EU",
    color: "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400",
  },
  fatf_blacklist: {
    label: "FATF High-Risk Jurisdictions (Black List)",
    short: "FATF Black",
    color: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
  },
  fatf_greylist: {
    label: "FATF Jurisdictions under Monitoring (Grey List)",
    short: "FATF Grey",
    color: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400",
  },
  opensanctions_default: {
    label: "OpenSanctions (aggregated)",
    short: "OpenSanctions",
    color: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400",
  },
  opensanctions_pep: {
    label: "OpenSanctions PEPs",
    short: "PEPs",
    color: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
  },
};

function EntityIcon({ type, className = "h-5 w-5" }: { type: string; className?: string }) {
  if (type === "individual") return <User className={`${className} text-muted-foreground`} />;
  if (type === "country") return <Globe className={`${className} text-muted-foreground`} />;
  return <Building2 className={`${className} text-muted-foreground`} />;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

// OpenSanctions dataset slugs → human-readable names. The full registry has
// hundreds of feeds; we name the common ones and fall back to a prettified
// version of the slug for the rest.
const DATASET_LABELS: Record<string, string> = {
  us_ofac_sdn: "OFAC SDN (US)",
  us_ofac_cons: "OFAC Consolidated Non-SDN (US)",
  us_trade_csl: "Consolidated Screening List (US)",
  us_bis_denied: "BIS Denied Persons (US)",
  us_bis_entity: "BIS Entity List (US)",
  us_sam_exclusions: "SAM Exclusions (US)",
  un_sc_sanctions: "UN Security Council",
  eu_fsf: "EU Financial Sanctions File",
  eu_travel_bans: "EU Travel Bans",
  eu_meps: "EU Members of Parliament",
  gb_hmt_sanctions: "UK HMT (OFSI)",
  gb_fcdo_sanctions: "UK FCDO",
  gb_coh: "UK Companies House",
  ca_dfatd_sema_sanctions: "Canada SEMA",
  au_dfat_sanctions: "Australia DFAT",
  ch_seco_sanctions: "Switzerland SECO",
  jp_mof_sanctions: "Japan MOF",
  fr_tresor_gels_avoir: "France Tresor",
  be_fod_sanctions: "Belgium FOD",
  mc_fund_freezes: "Monaco Fund Freezes",
  sg_mas_sanctions: "Singapore MAS",
  nz_dfat_sanctions: "New Zealand DFAT",
  ua_ws: "Ukraine NSDC",
  ru_war_register: "Russia War Register",
  interpol_red_notices: "Interpol Red Notices",
  worldbank_debarred: "World Bank Debarred",
};

function asStringArray(v: unknown): string[] {
  if (!v) return [];
  if (Array.isArray(v)) return v.filter((x): x is string => typeof x === "string" && x.length > 0);
  if (typeof v === "string") return [v];
  return [];
}

function firstString(v: unknown): string | null {
  const arr = asStringArray(v);
  return arr.length > 0 ? (arr[0] ?? null) : null;
}

function joinStrings(v: unknown, sep = ", "): string | null {
  const arr = asStringArray(v);
  return arr.length > 0 ? arr.join(sep) : null;
}

const IDENTITY_KEYS = [
  "birthDate", "birthPlace", "deathDate", "gender", "nationality",
  "idNumber", "passportNumber", "taxNumber", "registrationNumber", "leiCode",
  "imoNumber", "flag", "type", "incorporationDate", "dissolutionDate",
  "position", "address", "sourceUrl",
] as const;

function hasIdentityDetails(props: Record<string, unknown>): boolean {
  return IDENTITY_KEYS.some((k) => asStringArray(props[k]).length > 0);
}

function Field({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string | null;
  mono?: boolean;
}) {
  if (!value) return null;
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className={mono ? "font-mono text-sm break-all" : "text-sm font-medium"}>{value}</dd>
    </div>
  );
}

function humanizeDataset(slug: string): string {
  const known = DATASET_LABELS[slug];
  if (known) return known;
  return slug
    .split("_")
    .map((w) => (w.length <= 3 ? w.toUpperCase() : w.charAt(0).toUpperCase() + w.slice(1)))
    .join(" ");
}

export default function SanctionsEntryDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id;
  const [entry, setEntry] = useState<SanctionsEntry | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    setError(null);
    sanctionsApi
      .entry(id)
      .then(setEntry)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [id]);

  const sourceDef = entry ? SOURCE_LABELS[entry.source] : undefined;
  const isHighRisk = entry?.source === "fatf_blacklist";

  return (
    <div className="space-y-6">
      <Link
        href="/compliance/sanctions"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        Back to sanctions list
      </Link>

      {loading && (
        <div className="rounded-xl border bg-card p-8 text-center text-sm text-muted-foreground">
          Loading…
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:bg-red-900/20 dark:border-red-800 dark:text-red-400">
          {error}
        </div>
      )}

      {entry && (
        <>
          <div className="flex items-start gap-3">
            {isHighRisk ? (
              <ShieldAlert className="h-7 w-7 text-red-500 shrink-0 mt-1" />
            ) : (
              <ShieldCheck className="h-7 w-7 text-blue-500 shrink-0 mt-1" />
            )}
            <div className="min-w-0 flex-1">
              <h1 className="text-2xl font-semibold tracking-tight break-words">
                {entry.primary_name}
              </h1>
              <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
                <EntityIcon type={entry.entity_type} className="h-4 w-4" />
                <span className="capitalize">{entry.entity_type.replace("_", " ")}</span>
                <span>·</span>
                <span
                  className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${sourceDef?.color ?? "bg-muted text-muted-foreground"}`}
                >
                  {sourceDef?.label ?? entry.source}
                </span>
              </div>
            </div>
          </div>

          {/* Reference ID — long IDs from OpenSanctions can wrap */}
          <div className="rounded-xl border bg-card p-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-1">
              Reference ID
            </p>
            <p className="font-mono text-sm break-all">{entry.ref_id}</p>
          </div>

          {/* Period — when this entity was first observed and last changed
              upstream. NULL for non-OpenSanctions sources. */}
          {(entry.first_seen || entry.last_seen || entry.last_change) && (
            <div className="rounded-xl border bg-card p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-3">
                Period
              </p>
              <dl className="grid gap-3 sm:grid-cols-3 text-sm">
                {entry.first_seen && (
                  <div>
                    <dt className="text-xs text-muted-foreground">First seen</dt>
                    <dd className="font-medium">{formatDate(entry.first_seen)}</dd>
                  </div>
                )}
                {entry.last_seen && (
                  <div>
                    <dt className="text-xs text-muted-foreground">Last seen</dt>
                    <dd className="font-medium">{formatDate(entry.last_seen)}</dd>
                  </div>
                )}
                {entry.last_change && (
                  <div>
                    <dt className="text-xs text-muted-foreground">Last changed</dt>
                    <dd className="font-medium">{formatDate(entry.last_change)}</dd>
                  </div>
                )}
              </dl>
            </div>
          )}

          {/* Sanctioned by — upstream datasets containing this entity. */}
          {entry.datasets && entry.datasets.length > 0 && (
            <div className="rounded-xl border bg-card p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-3">
                Sanctioned by ({entry.datasets.length})
              </p>
              <div className="flex flex-wrap gap-1.5">
                {entry.datasets.map((d, i) => (
                  <span
                    key={i}
                    title={d}
                    className="inline-block rounded-md border bg-muted/40 px-2 py-1 text-xs font-medium"
                  >
                    {humanizeDataset(d)}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Identity details — pulled from OpenSanctions FtM properties. */}
          {entry.properties && hasIdentityDetails(entry.properties) && (
            <div className="rounded-xl border bg-card p-4 space-y-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Identity details
              </p>
              <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2 text-sm">
                <Field label="Birth date" value={firstString(entry.properties.birthDate)} />
                <Field label="Birth place" value={firstString(entry.properties.birthPlace)} />
                <Field label="Death date" value={firstString(entry.properties.deathDate)} />
                <Field label="Gender" value={firstString(entry.properties.gender)} />
                <Field label="Nationality" value={joinStrings(entry.properties.nationality)} />
                <Field label="ID number" value={firstString(entry.properties.idNumber)} mono />
                <Field
                  label="Passport number"
                  value={firstString(entry.properties.passportNumber)}
                  mono
                />
                <Field label="Tax number" value={firstString(entry.properties.taxNumber)} mono />
                <Field
                  label="Registration"
                  value={firstString(entry.properties.registrationNumber)}
                  mono
                />
                <Field label="LEI" value={firstString(entry.properties.leiCode)} mono />
                <Field label="IMO" value={firstString(entry.properties.imoNumber)} mono />
                <Field label="Flag" value={firstString(entry.properties.flag)} />
                <Field label="Type" value={firstString(entry.properties.type)} />
                <Field
                  label="Incorporated"
                  value={firstString(entry.properties.incorporationDate)}
                />
                <Field label="Dissolved" value={firstString(entry.properties.dissolutionDate)} />
              </dl>

              {/* Position / title — can be a long list of free-text strings. */}
              {asStringArray(entry.properties.position).length > 0 && (
                <div>
                  <p className="text-xs text-muted-foreground mb-1">Position / role</p>
                  <ul className="space-y-1 text-sm">
                    {asStringArray(entry.properties.position).map((p, i) => (
                      <li key={i} className="leading-snug">
                        {p}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Address — show all known. */}
              {asStringArray(entry.properties.address).length > 0 && (
                <div>
                  <p className="text-xs text-muted-foreground mb-1">Address</p>
                  <ul className="space-y-1 text-sm">
                    {asStringArray(entry.properties.address).map((a, i) => (
                      <li key={i} className="leading-snug">
                        {a}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Source URLs — clickable links to upstream listings. */}
              {asStringArray(entry.properties.sourceUrl).length > 0 && (
                <div>
                  <p className="text-xs text-muted-foreground mb-1">Source URLs</p>
                  <ul className="space-y-1 text-sm">
                    {asStringArray(entry.properties.sourceUrl).map((u, i) => (
                      <li key={i} className="truncate">
                        <a
                          href={u}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-blue-600 dark:text-blue-400 hover:underline break-all"
                        >
                          {u}
                        </a>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          {/* Aliases */}
          {entry.aliases.length > 0 && (
            <div className="rounded-xl border bg-card p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-3">
                Known aliases ({entry.aliases.length})
              </p>
              <ul className="space-y-1.5">
                {entry.aliases.map((a, i) => (
                  <li key={i} className="flex items-baseline gap-2">
                    <span className="text-xs text-muted-foreground shrink-0 w-16">{a.type}</span>
                    <span className="text-sm font-medium">{a.name}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Two-column grid for countries + programs */}
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="rounded-xl border bg-card p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">
                Countries
              </p>
              {entry.countries.length > 0 ? (
                <div className="flex flex-wrap gap-1.5">
                  {entry.countries.map((c, i) => (
                    <span
                      key={i}
                      className="inline-block rounded bg-muted px-2 py-0.5 text-xs uppercase tracking-wide"
                    >
                      {c}
                    </span>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">—</p>
              )}
            </div>

            <div className="rounded-xl border bg-card p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">
                Programs
              </p>
              {entry.programs.length > 0 ? (
                <div className="flex flex-wrap gap-1.5">
                  {entry.programs.map((p, i) => (
                    <span
                      key={i}
                      className="inline-block rounded bg-blue-50 dark:bg-blue-900/20 px-2 py-0.5 text-xs text-blue-700 dark:text-blue-400"
                    >
                      {p}
                    </span>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">—</p>
              )}
            </div>
          </div>

          {/* Remarks (free-text) */}
          {entry.remarks && (
            <div className="rounded-xl border bg-card p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">
                Remarks
              </p>
              <p className="text-sm whitespace-pre-wrap break-words">{entry.remarks}</p>
            </div>
          )}
        </>
      )}
    </div>
  );
}
