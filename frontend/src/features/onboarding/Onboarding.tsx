import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api, ApiError } from "../../lib/api";
import { LANGS, setLanguage } from "../../i18n";
import { useSession, type User } from "../../lib/session";
import { Banners } from "../../components/Layout";
import { Button, Card, ErrorBox, Field, inputCls, ProvenanceBadge } from "../../components/ui";

type Place = { node_id: string; name: string; node_type: string; district: string | null; provenance: string; needs_review: boolean };
const ROLE_ICON: Record<string, string> = { FARMER: "🧑‍🌾", SUPERVISOR: "📋", WAREHOUSE: "🏬", DISPATCHER: "🚚", NGO: "🤝", TRANSPORTER: "🛻" };
const ROLE_PLACE: Record<string, string> = {
  FARMER: "FarmGatherPoint", SUPERVISOR: "AssemblyMandi,ReceivingMarket", WAREHOUSE: "TransitStorageNode",
  DISPATCHER: "AssemblyMandi,ReceivingMarket", NGO: "NGOSink", TRANSPORTER: "",
};

export default function Onboarding() {
  const { t, i18n } = useTranslation();
  const nav = useNavigate();
  const { signIn, meta, user } = useSession();
  const [step, setStep] = useState<"lang" | "phone" | "code" | "role" | "profile" | "consent" | "perms">("lang");
  const [phone, setPhone] = useState("+91");
  const [challenge, setChallenge] = useState<{ challenge_id: string; dev_otp?: string } | null>(null);
  const [code, setCode] = useState("");
  const [roles, setRoles] = useState<{ role: string; description: string }[]>([]);
  const [role, setRole] = useState("");
  const [name, setName] = useState("");
  const [district, setDistrict] = useState("");
  const [nodeId, setNodeId] = useState("");
  const [commodities, setCommodities] = useState<string[]>(["tomato", "orange", "onion"]);
  const [places, setPlaces] = useState<Place[]>([]);
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  // Already signed in when arriving here → home. (Not after signing in during this flow: new users still see the
  // permission explanations and the tour.)
  useEffect(() => { if (user && (step === "lang" || step === "phone")) nav("/", { replace: true }); }, [user, step, nav]);
  useEffect(() => { void api("/roles").then(setRoles).catch(() => undefined); }, []);
  useEffect(() => {
    if (step === "profile" && ROLE_PLACE[role]) {
      void api<Place[]>(`/public/places?type=${ROLE_PLACE[role]}`).then(setPlaces).catch(setErr);
    }
  }, [step, role]);
  const districts = useMemo(() => [...new Set(places.map((p) => p.district).filter(Boolean))] as string[], [places]);
  const shown = places.filter((p) => !district || p.district === district);

  async function sendCode() {
    setErr(null); setBusy(true);
    try {
      setChallenge(await api("/auth/otp/request", { body: { phone: phone.replace(/\s/g, "") } }));
      setStep("code");
    } catch (e) { setErr(e); } finally { setBusy(false); }
  }
  async function verify(withProfile: boolean) {
    setErr(null); setBusy(true);
    try {
      const body: any = { challenge_id: challenge!.challenge_id, code };
      if (withProfile) body.profile = { role, name: name || null, language: i18n.language, district: district || null,
        home_node_id: nodeId || null, commodity_interests: commodities, consent: true };
      const r = await api<{ token: string; user: User }>("/auth/otp/verify", { body });
      setStep("perms");
      signIn(r.token, r.user);
      if (!withProfile) nav("/", { replace: true });   // returning user: straight home
    } catch (e) {
      if (e instanceof ApiError && e.code === "needs_profile") {
        // the code is consumed only on success, so ask for a fresh one after the profile
        setStep("role");
      } else setErr(e);
    } finally { setBusy(false); }
  }
  function finishProfile() {
    // The server did not consume the code when it answered "needs profile", so the same code completes sign-up
    // (valid for 5 minutes; if it expires the user is asked for a new one).
    setErr(null);
    setStep("consent");
  }

  return (
    <div className="min-h-full">
      <Banners />
      <div className="mx-auto max-w-lg space-y-4 p-4">
        <div className="flex items-center gap-3 pt-4">
          <img src={meta?.logo_path ?? "/logo-placeholder.svg"} alt="" className="size-10" />
          <h1 className="text-xl font-bold">{meta?.product_name ?? "PHL Platform"}</h1>
        </div>
        {err ? <ErrorBox error={err} /> : null}

        {step === "lang" && (
          <Card title={t("onb.chooseLanguage")}>
            <div className="grid gap-3">
              {LANGS.map((l) => (
                <Button key={l.code} variant={i18n.language === l.code ? "primary" : "secondary"} className="h-16 text-xl"
                  onClick={() => { setLanguage(l.code); setStep("phone"); }}>{l.label}</Button>
              ))}
            </div>
            <p className="mt-3 text-sm text-muted">{t("onb.translationNote")}</p>
          </Card>
        )}

        {step === "phone" && (
          <Card title={t("onb.phoneTitle")}>
            <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); void sendCode(); }}>
              <Field label={t("onb.phoneTitle")} hint={t("onb.phoneHint")}>
                {(id) => <input id={id} className={`${inputCls} text-lg tracking-wider`} inputMode="tel" autoComplete="tel"
                  value={phone} onChange={(e) => setPhone(e.target.value)} pattern="\+?[0-9 ]{10,16}" required />}
              </Field>
              <Button type="submit" busy={busy} className="w-full">{t("onb.sendCode")}</Button>
              {meta?.demo_mode ? <p className="text-sm text-muted">Demo personas: +910000000001 (farmer) … +910000000007 (analyst). See the Guided demo.</p> : null}
            </form>
          </Card>
        )}

        {step === "code" && challenge && (
          <Card title={t("onb.codeTitle")}>
            <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); void verify(false); }}>
              {challenge.dev_otp ? (
                <p className="rounded-lg bg-warn-soft p-2 text-warn" data-testid="dev-otp">{t("onb.devCode")}: <b className="font-mono text-lg">{challenge.dev_otp}</b></p>
              ) : null}
              <Field label={t("onb.codeTitle")}>
                {(id) => <input id={id} className={`${inputCls} text-center font-mono text-2xl tracking-[0.5em]`} inputMode="numeric"
                  autoComplete="one-time-code" maxLength={6} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} required />}
              </Field>
              <Button type="submit" busy={busy} className="w-full">{t("onb.verify")}</Button>
            </form>
          </Card>
        )}

        {step === "role" && (
          <Card title={t("onb.roleTitle")}>
            <div className="grid gap-2">
              {roles.map((r) => (
                <button key={r.role} onClick={() => { setRole(r.role); setStep("profile"); }}
                  className={`tap flex items-center gap-3 rounded-xl border p-3 text-left ${role === r.role ? "border-brand bg-brand-soft" : "border-line bg-surface-2"}`}>
                  <span className="text-3xl" aria-hidden>{ROLE_ICON[r.role]}</span>
                  <span><span className="block font-semibold">{t(`role.${r.role}`)}</span><span className="text-sm text-muted">{r.description}</span></span>
                </button>
              ))}
            </div>
          </Card>
        )}

        {step === "profile" && (
          <Card title={t("onb.profileTitle")}>
            <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); finishProfile(); }}>
              <Field label={t("onb.name")}>{(id) => <input id={id} className={inputCls} value={name} onChange={(e) => setName(e.target.value)} maxLength={120} />}</Field>
              {ROLE_PLACE[role] ? (
                <>
                  <Field label={t("onb.district")}>
                    {(id) => <select id={id} className={inputCls} value={district} onChange={(e) => { setDistrict(e.target.value); setNodeId(""); }}>
                      <option value="">All districts</option>{districts.map((d) => <option key={d}>{d}</option>)}
                    </select>}
                  </Field>
                  <Field label={t("onb.location")} hint={t("onb.locationHint")}>
                    {(id) => <select id={id} className={inputCls} value={nodeId} onChange={(e) => setNodeId(e.target.value)} required>
                      <option value="" disabled>Select…</option>
                      {shown.map((p) => <option key={p.node_id} value={p.node_id}>{p.name}{p.provenance === "SYNTHETIC_DEMO" ? " (DEMO)" : ""}{p.needs_review ? " (location under review)" : ""}</option>)}
                    </select>}
                  </Field>
                  {role === "NGO" && !shown.length ? <p className="text-sm text-muted">Few NGOs are mapped yet. Choose the demo NGO, or ask an admin to add yours.</p> : null}
                </>
              ) : null}
              <fieldset>
                <legend className="mb-2 font-semibold">{t("onb.commodities")}</legend>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(meta?.commodities ?? {}).map(([k, label]) => (
                    <label key={k} className={`tap flex cursor-pointer items-center gap-2 rounded-xl border px-3 ${commodities.includes(k) ? "border-brand bg-brand-soft" : "border-line"}`}>
                      <input type="checkbox" className="size-5" checked={commodities.includes(k)}
                        onChange={(e) => setCommodities((c) => e.target.checked ? [...c, k] : c.filter((x) => x !== k))} />{label}
                    </label>
                  ))}
                </div>
              </fieldset>
              <Button type="submit" busy={busy} className="w-full">{t("onb.continue")}</Button>
            </form>
          </Card>
        )}

        {step === "consent" && (
          <Card title={t("onb.consentTitle")}>
            <p>{t("onb.consent")}</p>
            <p className="mt-2 text-sm text-muted">This is a research prototype. Legal review of data handling is pending (see the Evidence & limits page).</p>

            <Button className="mt-4 w-full" busy={busy} onClick={() => void verify(true)}>{t("onb.agree")}</Button>
          </Card>
        )}

        {step === "perms" && <Permissions onDone={() => nav("/tour")} />}
        {nodeId && places.find((p) => p.node_id === nodeId)?.provenance ? (
          <p className="text-xs text-muted">Location data: <ProvenanceBadge p={places.find((p) => p.node_id === nodeId)?.provenance} /></p>
        ) : null}
      </div>
    </div>
  );
}

function Permissions({ onDone }: { onDone: () => void }) {
  const { t } = useTranslation();
  const [notif, setNotif] = useState<string>(typeof Notification !== "undefined" ? Notification.permission : "unsupported");
  return (
    <Card title={t("onb.permsTitle")}>
      <ul className="space-y-4">
        <li>
          <p>📷 {t("onb.camera")}</p>
          <p className="text-sm text-muted">We ask the first time you scan. You can always type the code instead.</p>
        </li>
        <li>
          <p>🔔 {t("onb.notifications")}</p>
          {notif === "default" ? (
            <div className="mt-2 flex gap-2">
              <Button variant="secondary" onClick={async () => setNotif(await Notification.requestPermission())}>{t("onb.allow")}</Button>
              <Button variant="ghost" onClick={() => setNotif("skipped")}>{t("onb.skip")}</Button>
            </div>
          ) : <p className="text-sm text-muted">Status: {notif}. In-app alerts work either way.</p>}
        </li>
        <li><p>📍 Location (GPS) is never required: your location comes from the place you picked.</p></li>
      </ul>
      <Button className="mt-4 w-full" onClick={onDone}>{t("onb.continue")}</Button>
    </Card>
  );
}
