import { expect, test, type Page } from "@playwright/test";
import { api, apiToken, clockNowIso, PERSONA, uiLogin } from "../e2e/helpers";

// Screenshots for the Stage-3 submission. Run with `python tasks.py capture` (isolated demo stack on :8001).
const OUT = "../submission/screenshots";
async function signOut(page: Page) {
  await page.evaluate(() => localStorage.removeItem("phl.token"));
}
const shot = (page: Page, name: string) => page.screenshot({ path: `${OUT}/${name}.png`, fullPage: false });

test.describe.configure({ mode: "serial" });

test("desktop screens", async ({ page, request }) => {
  test.setTimeout(240_000);
  await page.setViewportSize({ width: 1366, height: 860 });

  // Story data: run the guided demo end to end (creates lots, handovers, a rescue, a donation).
  await page.goto("/demo");
  for (let i = 0; i < 5; i++) {
    await page.getByTestId("demo-next").click();
    await expect(page.getByTestId("demo-log").locator("li").nth(i)).toBeVisible({ timeout: 30000 });
  }
  await page.waitForTimeout(500);
  await shot(page, "07_guided_demo");

  // Simulation lab as the analyst
  await page.getByTestId("demo-next").click();
  await expect(page.getByText("Verdict (pre-registered decision rule)")).toBeVisible();
  await shot(page, "10_lab_results");
  await page.getByRole("tab", { name: "Replay on map" }).click();
  await expect(page.getByTestId("replay-stats")).toBeVisible();
  await page.getByTestId("replay-busiest").click();
  await page.getByLabel("Map").first().scrollIntoViewIfNeeded();
  await page.mouse.wheel(0, 160);
  await page.waitForTimeout(4000);
  await shot(page, "11_lab_replay_flow_map");
  await page.getByRole("tab", { name: "Live run" }).click();
  await page.getByTestId("live-start").click();
  await expect(page.getByText(/Hour \d+ of/)).toBeVisible({ timeout: 30000 });
  await expect(page.getByText("Final (this live run)")).toBeVisible({ timeout: 60000 });
  await page.getByText("Wastage so far: baseline").scrollIntoViewIfNeeded();
  await page.mouse.wheel(0, -60);
  await page.waitForTimeout(800);
  await shot(page, "12_lab_live_dashboard");
  await page.getByTestId("live-busiest").click();
  await page.getByLabel("Map").last().scrollIntoViewIfNeeded();
  await page.mouse.wheel(0, 200);
  await page.waitForTimeout(3000);
  await shot(page, "13_lab_live_map");

  // Route advisor as the dispatcher
  await signOut(page);
  await uiLogin(page, PERSONA.dispatcher);
  await page.goto("/advisor");
  await page.getByLabel("Hours since harvest").fill("28");
  await page.getByRole("button", { name: "Compare routes" }).click();
  await expect(page.getByTestId("advisor-action")).toBeVisible({ timeout: 30000 });
  await page.waitForTimeout(3500);
  await shot(page, "09_route_advisor");

  // Crowd meter
  await page.goto("/crowd");
  await expect(page.getByText(/Mandi crowd meter/)).toBeVisible();
  await page.waitForTimeout(3500);
  await shot(page, "08_crowd_meter");

  // Evidence & limitations (public)
  await page.goto("/evidence");
  await expect(page.getByTestId("interview-statement")).toBeVisible();
  await shot(page, "14_evidence_limits");

  // Storage (warehouse) with a fresh, a warm and a hot lot so all three colours show
  const wh = await apiToken(request, PERSONA.warehouse);
  for (const [c, h] of [["onion", 6], ["orange", 30], ["tomato", 22]] as const) {
    await api(request, wh.token, "/consignments", { commodity: c, qty_kg: 800, harvest_time: await clockNowIso(request, h), origin_node_id: wh.user.home_node_id });
  }
  await signOut(page);
  await uiLogin(page, PERSONA.warehouse);
  await page.goto("/storage");
  await expect(page.locator("[data-light]").first()).toBeVisible();
  await shot(page, "05_storage_traffic_light");
  await page.getByText("How is this calculated?").first().click();
  await page.waitForTimeout(400);
  await shot(page, "06_shelf_life_explanation");
});

test("phone screens", async ({ page, request }) => {
  test.setTimeout(180_000);
  await page.setViewportSize({ width: 412, height: 915 });
  await page.goto("/welcome");
  await page.getByRole("button", { name: "English" }).waitFor();
  await shot(page, "01_onboarding_language");

  // farmer registers a lot → label with QR + PIN
  await uiLogin(page, PERSONA.farmer);
  await shot(page, "02_home_farmer");
  await page.goto("/lots/new");
  await page.getByRole("button", { name: /Tomato/ }).click();
  await page.getByLabel("Quantity (kg)").fill("1200");
  await page.getByRole("button", { name: "Register a lot" }).click();
  await expect(page.getByTestId("lot-label")).toBeVisible({ timeout: 15000 });
  await shot(page, "03_lot_label_qr_pin");

  // supervisor: lot journey + wastage logger
  const sup = await apiToken(request, PERSONA.supervisor);
  const f = await apiToken(request, PERSONA.farmer);
  const made = await api(request, f.token, "/consignments", { commodity: "tomato", qty_kg: 900, harvest_time: await clockNowIso(request, 14), origin_node_id: f.user.home_node_id });
  const h = await api(request, f.token, `/consignments/${made.consignment.id}/handovers`, { to_node_id: sup.user.home_node_id, weight_kg: 900, condition: "GOOD" });
  await api(request, sup.token, `/handovers/${h.id}/confirm`, { weight_kg: 895, condition: "GOOD" });
  await signOut(page);
  await uiLogin(page, PERSONA.supervisor);
  await page.goto(`/lots/${made.consignment.id}`);
  await page.locator("#waste-slider").fill("54");
  await page.getByRole("heading", { name: "Log wastage" }).scrollIntoViewIfNeeded();
  await shot(page, "04_wastage_logger");
  await page.getByRole("heading", { name: "Journey" }).scrollIntoViewIfNeeded();
  await page.waitForTimeout(3000);
  await shot(page, "04b_lot_journey_tamper_evident");

  // NGO offer with claim timer
  const ngo = await apiToken(request, PERSONA.ngo);
  void ngo;
  const wh = await apiToken(request, PERSONA.warehouse);
  const lot = await api(request, wh.token, "/consignments", { commodity: "tomato", qty_kg: 300, harvest_time: await clockNowIso(request, 8), origin_node_id: wh.user.home_node_id });
  await api(request, wh.token, "/rescue/broadcasts", { consignment_id: lot.consignment.id, trigger: "UNSOLD" });
  await signOut(page);
  await uiLogin(page, PERSONA.ngo);
  await page.goto("/rescue");
  await page.getByTestId("claim").first().click();
  await expect(page.getByTestId("claim-timer").first()).toBeVisible();
  await shot(page, "07b_ngo_claim_timer");
});
