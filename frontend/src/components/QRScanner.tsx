import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button, Field, inputCls } from "./ui";

/** Camera QR scan with a permission explanation *before* the OS prompt, and a manual code + PIN fallback. */
export function QRScanner({ onCode, onManual }: { onCode: (shortCode: string) => void; onManual: (code: string, pin: string) => void }) {
  const { t } = useTranslation();
  const video = useRef<HTMLVideoElement>(null);
  const [mode, setMode] = useState<"primer" | "camera" | "manual">(
    hasCamera() ? "primer" : "manual");
  const [err, setErr] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [pin, setPin] = useState("");

  useEffect(() => {
    if (mode !== "camera" || !video.current) return;
    let stop: (() => void) | undefined;
    let cancelled = false;
    void import("@zxing/browser").then(async ({ BrowserQRCodeReader }) => {
      try {
        const reader = new BrowserQRCodeReader();
        const controls = await reader.decodeFromVideoDevice(undefined, video.current!, (res) => {
          if (!res || cancelled) return;
          const text = res.getText();
          const m = /^PHL1:([0-9A-Z]{6,12})$/.exec(text.trim());
          if (m) {
            controls.stop();
            onCode(m[1]);
          } else {
            setErr("This QR code is not a lot label from this app.");
          }
        });
        stop = () => controls.stop();
      } catch {
        setErr(t("scan.cameraOff"));
        setMode("manual");
      }
    });
    return () => {
      cancelled = true;
      stop?.();
    };
  }, [mode, onCode, t]);

  if (mode === "primer") {
    return (
      <div className="space-y-3">
        <p>{t("onb.camera")}</p>
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => setMode("camera")}>📷 {t("onb.allow")}</Button>
          <Button variant="secondary" onClick={() => setMode("manual")}>{t("scan.manual")}</Button>
        </div>
      </div>
    );
  }
  if (mode === "camera") {
    return (
      <div className="space-y-3">
        <video ref={video} className="aspect-square w-full max-w-sm rounded-xl bg-black object-cover" muted playsInline aria-label="Camera preview" />
        {err ? <p role="alert" className="text-bad">{err}</p> : <p className="text-sm text-muted">Point the camera at the QR label.</p>}
        <Button variant="secondary" onClick={() => setMode("manual")}>{t("scan.manual")}</Button>
      </div>
    );
  }
  return (
    <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); onManual(code.trim(), pin.trim()); }}>
      {err ? <p className="text-sm text-muted">{err}</p> : null}
      <Field label={t("scan.code")}>
        {(id) => <input id={id} className={`${inputCls} font-mono uppercase tracking-widest`} value={code} onChange={(e) => setCode(e.target.value)}
          autoCapitalize="characters" autoComplete="off" placeholder="e.g. 7K3M9QX2" required minLength={6} maxLength={14} />}
      </Field>
      <Field label={t("scan.pin")} hint="4 digits, written on the label">
        {(id) => <input id={id} className={`${inputCls} font-mono tracking-widest`} value={pin} onChange={(e) => setPin(e.target.value.replace(/\D/g, ""))}
          inputMode="numeric" autoComplete="one-time-code" required minLength={4} maxLength={8} />}
      </Field>
      <Button type="submit">{t("scan.find")}</Button>
      {hasCamera() ? (
        <Button type="button" variant="ghost" onClick={() => { setErr(null); setMode("camera"); }}>📷 Use camera</Button>
      ) : null}
    </form>
  );
}

function hasCamera(): boolean {
  return typeof navigator !== "undefined" && typeof navigator.mediaDevices?.getUserMedia === "function";
}
