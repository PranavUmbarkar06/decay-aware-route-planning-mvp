import { expect, type APIRequestContext, type Page } from "@playwright/test";

export const PERSONA = {
  farmer: "+910000000001", supervisor: "+910000000002", warehouse: "+910000000003", dispatcher: "+910000000004",
  ngo: "+910000000005", driver: "+910000000006", admin: "+910000000007",
};

export function freshPhone(): string {
  return `+9100001${String(Math.floor(Math.random() * 1e5)).padStart(5, "0")}`;
}

/** Sign in through the real UI (language → phone → on-screen DEV code). Returns once on the home page. */
export async function uiLogin(page: Page, phone: string) {
  await page.goto("/welcome");
  await page.getByRole("button", { name: "English" }).click();
  await page.getByLabel("Your phone number").fill(phone);
  await page.getByRole("button", { name: "Send code" }).click();
  const dev = await page.getByTestId("dev-otp").innerText();
  const code = dev.match(/(\d{6})/)![1];
  await page.getByLabel("Enter the 6-digit code").fill(code);
  await page.getByRole("button", { name: "Verify" }).click();
  await expect(page.getByRole("heading", { name: "Home" })).toBeVisible();
}

/** API sign-in (for setting up state quickly). */
export async function apiToken(request: APIRequestContext, phone: string): Promise<{ token: string; user: any }> {
  const ch = await (await request.post("/api/v1/auth/otp/request", { data: { phone } })).json();
  const r = await (await request.post("/api/v1/auth/otp/verify", { data: { challenge_id: ch.challenge_id, code: ch.dev_otp } })).json();
  return r;
}

export async function api(request: APIRequestContext, token: string, path: string, data?: unknown, method = data ? "POST" : "GET") {
  const res = await request.fetch(`/api/v1${path}`, { method, data, headers: { Authorization: `Bearer ${token}` } });
  expect(res.status(), `${method} ${path}: ${await res.text()}`).toBeLessThan(400);
  return res.json();
}

export async function clockNowIso(request: APIRequestContext, hoursAgo = 0): Promise<string> {
  const c = await (await request.get("/api/v1/clock")).json();
  return new Date(new Date(`${c.now_utc}Z`).getTime() - hoursAgo * 3600e3).toISOString();
}
