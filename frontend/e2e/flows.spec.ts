import { expect, test } from "@playwright/test";
import { api, apiToken, clockNowIso, freshPhone, PERSONA, uiLogin } from "./helpers";

for (const role of [
  { label: "Collection supervisor", place: true },
  { label: "NGO / community kitchen", place: true },
  { label: "Dispatcher", place: true },
  { label: "Driver", place: false },
]) {
  test(`onboarding: new ${role.label}`, async ({ page }) => {
    await page.goto("/welcome");
    await expect(page.getByTestId("demo-banner")).toBeVisible();
    await expect(page.getByTestId("devauth-banner")).toBeVisible();
    await page.getByRole("button", { name: "English" }).click();
    await page.getByLabel("Your phone number").fill(freshPhone());
    await page.getByRole("button", { name: "Send code" }).click();
    const code = (await page.getByTestId("dev-otp").innerText()).match(/(\d{6})/)![1];
    await page.getByLabel("Enter the 6-digit code").fill(code);
    await page.getByRole("button", { name: "Verify" }).click();
    await page.getByRole("button", { name: new RegExp(role.label) }).click();
    if (role.place) {
      const sel = page.getByLabel("Your location");
      await expect(sel.locator("option").nth(1)).toBeAttached();
      await sel.selectOption({ index: 1 });
    }
    await page.getByRole("button", { name: "Continue" }).click();
    await expect(page.getByRole("heading", { name: "How we use your data" })).toBeVisible();
    await page.getByRole("button", { name: "I agree" }).click();
    await expect(page.getByRole("heading", { name: "Permissions" })).toBeVisible();
    await page.getByRole("button", { name: "Continue" }).click();
    await expect(page.getByText("Quick tour (demo data)")).toBeVisible();
    await page.getByRole("button", { name: "Skip" }).click();
    await expect(page.getByRole("heading", { name: "Home" })).toBeVisible();
  });
}

test("QR handshake with manual code + PIN fallback, then two-party handover", async ({ page, browser, request }) => {
  page.on("pageerror", (e) => console.log("PAGEERROR", e.message));
  page.on("console", (m) => { if (m.type() === "error") console.log("CONSOLE", m.text()); });
  await uiLogin(page, PERSONA.farmer);
  await page.goto("/lots/new");
  await page.getByRole("button", { name: /Tomato/ }).click();
  await page.getByLabel("Quantity (kg)").fill("640");
  await page.getByRole("button", { name: "Register a lot" }).click();
  const label = page.getByTestId("lot-label");
  await expect(label).toBeVisible({ timeout: 15000 });
  const pin = await page.getByTestId("lot-pin").innerText();
  const code = (await label.locator(".font-mono").first().innerText()).trim();
  expect(pin).toMatch(/^\d{4}$/);

  // farmer hands over to the demo supervisor's mandi
  const sup = await apiToken(request, PERSONA.supervisor);
  await page.getByRole("link", { name: "Open lot" }).click();
  await page.getByLabel("Send to").selectOption(sup.user.home_node_id);
  await page.getByRole("button", { name: "Hand over" }).click();
  await expect(page.getByText("Handed over. The receiver must confirm.")).toBeVisible();

  // supervisor (separate phone) finds it by typing the code + PIN (camera fallback) and confirms receipt
  const ctx = await browser.newContext({ ...(test.info().project.use as any) });
  const p2 = await ctx.newPage();
  await uiLogin(p2, PERSONA.supervisor);
  await p2.goto("/scan");
  await p2.getByRole("button", { name: "Type the code instead" }).click();
  await p2.getByLabel("Lot code").fill(code.toLowerCase());
  await p2.getByLabel("PIN").fill(pin);
  await p2.getByRole("button", { name: "Find lot" }).click();
  await expect(p2.getByRole("heading", { name: "Confirm receipt" })).toBeVisible();
  await p2.getByRole("button", { name: "Confirm receipt" }).last().click();
  await expect(p2.getByText("Receipt confirmed")).toBeVisible();
  await expect(p2.getByText("Tamper-evident log verifies")).toBeVisible();
  await ctx.close();
});

test("wastage logger: slider + picture button + undo", async ({ page, request }) => {
  const sup = await apiToken(request, PERSONA.supervisor);
  const made = await api(request, sup.token, "/consignments", { commodity: "onion", qty_kg: 500, harvest_time: await clockNowIso(request, 4), origin_node_id: sup.user.home_node_id });
  await uiLogin(page, PERSONA.supervisor);
  await page.goto(`/lots/${made.consignment.id}`);
  const slider = page.locator("#waste-slider");
  await slider.fill("50");
  await expect(page.getByTestId("waste-kg")).toHaveText("50 kg");
  await page.locator('[data-reason="CRUSHED"]').click();
  await expect(page.getByText(/Logged 50 kg as Crushed in transit/)).toBeVisible();
  await page.getByRole("button", { name: "Undo" }).click();
  await expect(page.getByText("Undone")).toBeVisible();
  const c = await api(request, sup.token, `/consignments/${made.consignment.id}`);
  expect(c.wasted_kg).toBe(0);
  expect(c.current_qty_kg).toBe(500);
});

test("claim race: two NGO coordinators claim at once, exactly one wins", async ({ browser, request }) => {
  // a second fictional NGO coordinator at the demo NGO node
  const ngo1 = await apiToken(request, PERSONA.ngo);
  const extraPhone = freshPhone();
  const ch = await (await request.post("/api/v1/auth/otp/request", { data: { phone: extraPhone } })).json();
  await request.post("/api/v1/auth/otp/verify", { data: { challenge_id: ch.challenge_id, code: ch.dev_otp,
    profile: { role: "NGO", consent: true, home_node_id: ngo1.user.home_node_id } } });
  const wh = await apiToken(request, PERSONA.warehouse);
  const made = await api(request, wh.token, "/consignments", { commodity: "tomato", qty_kg: 300, harvest_time: await clockNowIso(request, 6), origin_node_id: wh.user.home_node_id });
  const b = await api(request, wh.token, "/rescue/broadcasts", { consignment_id: made.consignment.id, trigger: "UNSOLD" });
  expect(b.offers.some((o: any) => o.status === "OFFERED")).toBeTruthy();

  const pages = [];
  for (const phone of [PERSONA.ngo, extraPhone]) {
    const ctx = await browser.newContext({ ...(test.info().project.use as any) });
    const p = await ctx.newPage();
    await uiLogin(p, phone);
    await p.goto("/rescue");
    await expect(p.getByTestId("claim").first()).toBeVisible();
    pages.push(p);
  }
  await Promise.all(pages.map((p) => p.getByTestId("claim").first().click()));
  const outcomes = await Promise.all(pages.map(async (p) => {
    const won = p.getByText("Claimed. Collect it and scan the label at pickup.");
    const lost = p.getByText(/Another NGO claimed this lot first|Offer is claimed|already/);
    await expect(won.or(lost)).toBeVisible();
    return (await won.isVisible()) ? "won" : "lost";
  }));
  expect(outcomes.filter((o) => o === "won")).toHaveLength(1);
  await Promise.all(pages.map((p) => p.context().close()));
});

test("offline handover is queued with its real scan time and syncs on reconnect", async ({ page, context, request }) => {
  const f = await apiToken(request, PERSONA.farmer);
  const sup = await apiToken(request, PERSONA.supervisor);
  const made = await api(request, f.token, "/consignments", { commodity: "orange", qty_kg: 200, harvest_time: await clockNowIso(request, 10), origin_node_id: f.user.home_node_id });
  await uiLogin(page, PERSONA.farmer);
  await page.goto(`/lots/${made.consignment.id}`);
  await page.getByLabel("Send to").selectOption(sup.user.home_node_id);
  await context.setOffline(true);
  await page.evaluate(() => window.dispatchEvent(new Event("offline")));
  await page.getByRole("button", { name: "Hand over" }).click();
  await expect(page.getByText(/Saved offline with the real scan time/)).toBeVisible();
  await expect(page.getByTestId("offline-banner")).toBeVisible();
  await context.setOffline(false);
  await page.evaluate(() => window.dispatchEvent(new Event("online")));
  await expect(page.getByText(/Synced 1 offline action/)).toBeVisible({ timeout: 15000 });
  const tl = await api(request, f.token, `/consignments/${made.consignment.id}/timeline`);
  const rel = tl.events.find((e: any) => e.event_type === "RELEASE");
  expect(rel).toBeTruthy();
  expect(new Date(`${rel.sync_time_utc}Z`).getTime()).toBeGreaterThanOrEqual(new Date(`${rel.scan_time_utc}Z`).getTime() - 1000);
});

test("guided demo runs all six steps", async ({ page }) => {
  await page.goto("/demo");
  for (let i = 0; i < 5; i++) {
    await page.getByTestId("demo-next").click();
    await expect(page.getByTestId("demo-log").locator("li").last()).toBeVisible();
    await expect(page.getByTestId("demo-next").or(page.getByText("Demo complete"))).toBeEnabled({ timeout: 30000 });
  }
  await expect(page.getByTestId("demo-log")).toContainText("booked as DONATED");
  await page.getByTestId("demo-next").click();
  await expect(page).toHaveURL(/\/lab$/);
  await expect(page.getByText("Verdict (pre-registered decision rule)")).toBeVisible();
});

test("evidence page states that dispatcher needs are not validated", async ({ page }) => {
  await page.goto("/evidence");
  await expect(page.getByTestId("interview-statement")).toContainText("have not yet been validated by interviews");
});
