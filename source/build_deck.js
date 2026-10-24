// IMPACT TANK '26 – Round 1 Problem Brief deck generator
const path = require("path");
const pptxgen = require("pptxgenjs");
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const sharp = require("sharp");
const fa = require("react-icons/fa");
const { applyTheme } = require(process.env.PPTX_SKILL + "/scripts/apply_theme.js");

const OUT = process.argv[2] || "deck.pptx";

const THEME = {
  name: "Journey After Harvest",
  headFontFace: "Cambria",
  bodyFontFace: "Calibri",
  colors: {
    dk1: "1B2430", lt1: "FFFFFF", dk2: "12263A", lt2: "EEF3F5",
    accent1: "0F8B8D", accent2: "4CC3CF", accent3: "D9A21B", accent4: "B9472E",
    accent5: "5E6E7E", accent6: "D3E2E6", hlink: "0F8B8D", folHlink: "5E6E7E",
  },
};
const HEX = THEME.colors;

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.333 x 7.5
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
pres.title = "The Journey After Harvest – Problem Brief";
pres.subject = "IMPACT TANK '26 Round 1 – Problem Discovery";
pres.author = "[Team name]";
const C = pres.SchemeColor;

// ---------- icons ----------
async function icon(Comp, color = "FFFFFF", size = 256) {
  const svg = ReactDOMServer.renderToStaticMarkup(React.createElement(Comp, { color: "#" + color, size: String(size) }));
  const buf = await sharp(Buffer.from(svg)).png().toBuffer();
  return "image/png;base64," + buf.toString("base64");
}
async function iconCircle(slide, Comp, x, y, d, fill, name, iconColor = "FFFFFF") {
  slide.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color: fill }, line: { type: "none" }, objectName: name + " circle" });
  const pad = d * 0.25;
  slide.addImage({ data: await icon(Comp, iconColor), x: x + pad, y: y + pad, w: d - 2 * pad, h: d - 2 * pad, objectName: name + " icon" });
}

// ---------- layouts ----------
const FOOTER = "IMPACT TANK ’26  ·  Round 1 Problem Brief  ·  [Team name]";
pres.defineSlideMaster({
  title: "Dark",
  background: { color: HEX.dk2 },
  objects: [],
});
pres.defineSlideMaster({
  title: "Content",
  background: { color: HEX.lt1 },
  margin: [0.4, 0.6, 0.5, 0.6],
  objects: [
    { placeholder: { options: { name: "kicker", type: "body", x: 0.6, y: 0.32, w: 7.6, h: 0.32, fontSize: 12, bold: true, color: C.accent1, charSpacing: 2, margin: 0, valign: "middle" }, text: "" } },
    { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 0.66, w: 12.13, h: 0.9, fontFace: THEME.headFontFace, fontSize: 26, bold: true, color: C.text2, margin: 0, valign: "middle", align: "left" }, text: "" } },
    { text: { text: FOOTER, options: { x: 0.6, y: 7.08, w: 8, h: 0.28, fontSize: 9, color: C.accent5, margin: 0, valign: "middle" } } },
  ],
  slideNumber: { x: 12.23, y: 7.08, w: 0.5, h: 0.28, fontSize: 9, color: C.accent5, align: "right", margin: 0 },
});

// ---------- helpers ----------
const TAGS = {
  DOC: { label: "DOCUMENTED", w: 1.08, fill: C.accent1, color: C.background1, line: C.accent1 },
  INT: { label: "INTERPRETATION", w: 1.3, fill: C.background1, color: C.text2, line: C.text2 },
  HYP: { label: "HYPOTHESIS · VALIDATE", w: 1.68, fill: C.accent3, color: C.text1, line: C.accent3 },
};
function tag(slide, kind, x, y) {
  const t = TAGS[kind];
  slide.addText(t.label, {
    shape: pres.shapes.ROUNDED_RECTANGLE, rectRadius: 0.12, x, y, w: t.w, h: 0.23,
    fill: { color: t.fill }, line: { color: t.line, width: 0.75 }, color: t.color,
    fontSize: 8, bold: true, charSpacing: 1, align: "center", valign: "middle", margin: 0, isTextBox: true,
    objectName: "Evidence tag " + t.label,
  });
  return t.w;
}
function legend(slide) {
  let x = 12.73 - (TAGS.DOC.w + TAGS.INT.w + TAGS.HYP.w + 0.16);
  slide.addText("Evidence key", { x: x - 1.0, y: 0.36, w: 0.92, h: 0.23, fontSize: 9, color: C.accent5, align: "right", valign: "middle", margin: 0, isTextBox: true });
  x += tag(slide, "DOC", x, 0.36) + 0.08;
  x += tag(slide, "INT", x, 0.36) + 0.08;
  tag(slide, "HYP", x, 0.36);
}
function source(slide, text) {
  slide.addText(text, { x: 0.6, y: 6.63, w: 12.13, h: 0.38, fontSize: 9.5, color: C.accent5, valign: "top", margin: 0, isTextBox: true, objectName: "Source line" });
}
function content(kicker, title, section) {
  const s = pres.addSlide({ masterName: "Content", sectionTitle: section });
  s.addText(kicker, { placeholder: "kicker" });
  s.addText(title, { placeholder: "title" });
  return s;
}
function card(slide, x, y, w, h, fill = C.background2, name = "card") {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.08, fill: { color: fill }, line: { type: "none" }, objectName: name });
}

(async () => {
  // =====================================================================
  // 1. TITLE
  // =====================================================================
  pres.addSection({ title: "The problem" });
  {
    const s = pres.addSlide({ masterName: "Dark", sectionTitle: "The problem" });
    s.addText("IMPACT TANK ’26  ·  ROUND 1  ·  PROBLEM DISCOVERY BRIEF", { x: 0.7, y: 0.6, w: 8, h: 0.35, fontSize: 13, bold: true, color: C.accent2, charSpacing: 2, margin: 0, isTextBox: true });
    s.addText("The Journey After Harvest", { x: 0.7, y: 1.2, w: 8.0, h: 1.0, fontFace: THEME.headFontFace, fontSize: 42, bold: true, color: C.background1, margin: 0, isTextBox: true });
    s.addText("Why perishable fruit and vegetables lose quality and value between the mandi and the receiving market in India — and why that loss is still poorly understood", { x: 0.7, y: 2.35, w: 7.3, h: 1.35, fontSize: 19, color: C.accent6, margin: 0, valign: "top", isTextBox: true });

    // hook stat
    card(s, 8.75, 1.25, 3.9, 2.85, "1D3A52", "Hook stat card");
    s.addText("19.3 Mt", { x: 9.0, y: 1.42, w: 3.45, h: 0.8, fontFace: THEME.headFontFace, fontSize: 44, bold: true, color: C.accent2, margin: 0, isTextBox: true });
    s.addText("million tonnes (Mt) of fruit and vegetables lost after harvest in India each year, across all stages from farm to retail", { x: 9.0, y: 2.2, w: 3.45, h: 1.05, fontSize: 14, color: C.background1, margin: 0, valign: "top", isTextBox: true });
    s.addText("NABCONS for MoFPI, reference period 2020–22 (fruits 7.36 Mt + vegetables 11.97 Mt) [1]", { x: 9.0, y: 3.3, w: 3.45, h: 0.6, fontSize: 10, color: C.accent6, margin: 0, valign: "top", isTextBox: true });

    // journey motif: four stops
    const stops = [[fa.FaSeedling, "Farm"], [fa.FaWarehouse, "Assembly mandi"], [fa.FaTruck, "Road transit"], [fa.FaStore, "Receiving market"]];
    const y0 = 4.6, x0 = 0.95, step = 2.05;
    s.addShape(pres.shapes.LINE, { x: x0 + 0.3, y: y0 + 0.3, w: step * 3, h: 0, line: { color: HEX.accent5, width: 1.5, dashType: "dash" }, objectName: "Journey line" });
    for (let i = 0; i < stops.length; i++) {
      const hi = i >= 1;
      await iconCircle(s, stops[i][0], x0 + i * step, y0, 0.6, hi ? C.accent1 : "2B4660", "Journey stop " + (i + 1));
      s.addText(stops[i][1], { x: x0 + i * step - 0.55, y: y0 + 0.68, w: 1.7, h: 0.3, fontSize: 12, color: hi ? C.background1 : C.accent6, align: "center", margin: 0, isTextBox: true });
    }
    s.addText("This brief focuses on the stretch from aggregation to sale", { x: x0 + step - 0.2, y: y0 - 0.45, w: 4.6, h: 0.3, fontSize: 11, italic: true, color: C.accent2, margin: 0, isTextBox: true });

    s.addText([
      { text: "Team: ", options: { bold: true, color: C.accent2 } }, { text: "[Team name]", options: { breakLine: true } },
      { text: "Members: ", options: { bold: true, color: C.accent2 } }, { text: "[Member 1]  ·  [Member 2]  ·  [Member 3]  ·  [Member 4]  ·  [Member 5]", options: { breakLine: true } },
      { text: "Institution: ", options: { bold: true, color: C.accent2 } }, { text: "[College / University]" },
    ], { x: 0.7, y: 5.95, w: 9, h: 0.95, fontSize: 13, color: C.background1, margin: 0, valign: "top", paraSpaceAfter: 2, isTextBox: true });
    s.addNotes("Open with the journey, not the waste headline. India loses about 19.3 million tonnes of fruits and vegetables a year after harvest (NABCONS 2022, ref. period 2020-22). That number covers every stage from farm to retail, so we are NOT claiming it all happens in transport. Our brief zooms in on one leg: from the assembly mandi to the receiving market. Over the next slides we show why that leg matters, who is affected, and what nobody yet knows about it. Note for us: there is no solution in this deck. That is deliberate.");
  }

  // =====================================================================
  // 2. WHAT EXACTLY IS THE PROBLEM
  // =====================================================================
  {
    const s = content("01  ·  THE PROBLEM", "Perishable loads lose value between dispatch and sale", "The problem");
    legend(s);
    s.addText("PROBLEM STATEMENT", { x: 0.6, y: 1.75, w: 4, h: 0.3, fontSize: 12, bold: true, color: C.accent5, charSpacing: 2, margin: 0, isTextBox: true });
    const rows = [
      ["TARGET USER", "Dispatchers of perishable fruit and vegetable consignments: commission agents, traders and FPO marketing staff who send produce from assembly mandis to distant wholesale markets", "INT"],
      ["FACE DIFFICULTY WITH", "getting each load to a market where it arrives still saleable and fetches a fair price", "DOC"],
      ["BECAUSE OF", "transit time, heat, handling and destination-market conditions that vary after dispatch, in mostly non-refrigerated trucks, and that are poorly measured or visible when the decision is made", "HYP"],
      ["RESULTING IN", "quality downgrades, distress sales and wastage, with costs falling largely on farmers and traders and reaching consumers as price volatility", "DOC"],
    ];
    let y = 2.1;
    for (const [lab, txt, k] of rows) {
      s.addShape(pres.shapes.RECTANGLE, { x: 0.6, y, w: 1.85, h: 1.0, fill: { color: C.text2 }, line: { type: "none" }, objectName: "Label " + lab });
      s.addText(lab, { x: 0.72, y: y + 0.1, w: 1.65, h: 0.5, fontSize: 12, bold: true, color: C.background1, margin: 0, valign: "top", isTextBox: true });
      tag(s, k, 0.72, y + 0.66);
      s.addShape(pres.shapes.RECTANGLE, { x: 2.45, y, w: 5.85, h: 1.0, fill: { color: C.background2 }, line: { type: "none" }, objectName: "Statement " + lab });
      s.addText(txt, { x: 2.6, y, w: 5.6, h: 1.0, fontSize: 13.5, color: C.text1, margin: 0, valign: "middle", isTextBox: true });
      y += 1.12;
    }
    // scope card
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 8.65, y: 1.75, w: 4.08, h: 4.71, rectRadius: 0.08, fill: { color: C.background1 }, line: { color: C.accent6, width: 1.25 }, objectName: "Scope card" });
    await iconCircle(s, fa.FaCheck, 8.88, 1.95, 0.38, C.accent1, "In scope");
    s.addText("IN SCOPE", { x: 9.35, y: 1.95, w: 3, h: 0.38, fontSize: 13, bold: true, color: C.accent1, margin: 0, valign: "middle", isTextBox: true });
    const bl = (arr) => arr.map((t, i) => ({ text: t, options: { bullet: { indent: 12 }, breakLine: i < arr.length - 1 } }));
    s.addText(bl([
      "Highly perishable fruit & vegetables (e.g. tomato, guava, banana, mango, gourds)",
      "Road movement after first aggregation, up to sale at the receiving market",
      "Ambient (non-reefer) transport, the dominant mode [4]",
      "Variation by distance, season and region",
    ]), { x: 8.88, y: 2.4, w: 3.7, h: 1.95, fontSize: 12, color: C.text1, margin: 0, valign: "top", paraSpaceAfter: 3, isTextBox: true });
    await iconCircle(s, fa.FaTimes, 8.88, 4.4, 0.38, C.accent4, "Out of scope");
    s.addText("OUT OF SCOPE", { x: 9.35, y: 4.4, w: 3, h: 0.38, fontSize: 13, bold: true, color: C.accent4, margin: 0, valign: "middle", isTextBox: true });
    s.addText(bl([
      "Grains & pulses: market-stage loss only ≈0.6–1.2% [1]",
      "Farm-level harvest losses; household waste",
      "Long-term cold storage of potato and onion",
      "Any proposed solution",
    ]), { x: 8.88, y: 4.85, w: 3.7, h: 1.5, fontSize: 12, color: C.text1, margin: 0, valign: "top", paraSpaceAfter: 3, isTextBox: true });
    source(s, "Tags show how firmly each part is supported. The “because” clause mixes documented transit factors [3] with an untested claim about visibility at dispatch. Sources: [1] NABCONS 2022 via PIB 2025; [3] WRI India 2024; [4] NCCD 2015.");
    s.addNotes("Read the statement once, slowly. Then explain the tags. Target user is our framing choice (interpretation): we picked the dispatcher because the decision about where, when and how a load moves is made there. The difficulty and the consequences are documented in published fieldwork (WRI 2024, RBI 2024). The 'because' clause is partly a hypothesis: transit heat, delays and handling are documented, but the claim that dispatchers lack visibility of conditions ahead has not been tested yet, and we say so. Scope: perishable fruit and vegetables, the road leg after aggregation, ambient trucks. Grains are out because their market-stage losses are 0.6 to 1.2 percent, a different problem.");
  }

  // =====================================================================
  // 3. CONTEXT – JOURNEY
  // =====================================================================
  {
    const s = content("02  ·  CONTEXT", "Where it happens: failure points from mandi to market", "The problem");
    legend(s);
    const colW = 1.855, gap = 0.2, x0 = 0.6;
    const X = (i) => x0 + i * (colW + gap);
    // focus band
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: X(1) - 0.1, y: 1.62, w: 4 * colW + 3 * gap + 0.2, h: 4.35, rectRadius: 0.08, fill: { color: C.background2 }, line: { type: "none" }, objectName: "Focus band" });
    s.addText("FOCUS OF THIS BRIEF", { x: X(1), y: 1.67, w: 3, h: 0.25, fontSize: 9.5, bold: true, color: C.accent1, charSpacing: 2, margin: 0, isTextBox: true });
    const stages = [
      [fa.FaSeedling, "Farm & harvest", ""],
      [fa.FaWarehouse, "Assembly mandi", "aggregation, sale to trader"],
      [fa.FaBoxOpen, "Packing & dispatch", "loading, choice of market"],
      [fa.FaTruck, "Road transit", "hours to days"],
      [fa.FaDoorOpen, "Market entry", "waiting, unloading"],
      [fa.FaStore, "Wholesale → retail", "sale, resale"],
    ];
    for (let i = 0; i < 6; i++) {
      const cx = X(i) + colW / 2;
      if (i < 5) s.addShape(pres.shapes.LINE, { x: cx + 0.4, y: 2.4, w: colW + gap - 0.8, h: 0, line: { color: HEX.accent5, width: 1.25, endArrowType: "triangle" }, objectName: "Flow arrow " + i });
      await iconCircle(s, stages[i][0], cx - 0.35, 2.05, 0.7, i === 0 || i === 5 ? C.accent5 : C.accent1, "Stage " + (i + 1));
      s.addText(stages[i][1], { x: X(i), y: 2.82, w: colW, h: 0.3, fontSize: 13, bold: true, color: C.text2, align: "center", margin: 0, isTextBox: true });
      s.addText(stages[i][2], { x: X(i), y: 3.1, w: colW, h: 0.25, fontSize: 10, italic: true, color: C.accent5, align: "center", margin: 0, isTextBox: true });
    }
    const cards = [
      [["Harvest maturity is chosen to suit travel distance [3]", "DOC"], ["Farm stage carries the largest share of tomato loss: 8.37% [1]", "DOC"]],
      [["Poor sorting and grading at origin show up later as transit loss [3]", "DOC"], ["Destination picked without sight of arrivals at other markets", "HYP"]],
      [["Crates vs polythene bags; crates overfilled when paid per crate [3]", "DOC"], ["Non-refrigerated trucks; none used in the study area [3]", "DOC"]],
      [["Heat and vibration on poor roads damage produce [3]", "DOC"], ["Delays from inter-state permits, traffic and breakdowns [3]", "DOC"]],
      [["Waiting outside the market; trade mostly in morning hours [3]", "DOC"], ["No storage at the market, so unsold lots go at distress prices [3]", "DOC"]],
      [["A glut on arrival lowers price; damaged lots sell for less [3]", "DOC"], ["Delhi receives tomato all year from many states; long hauls are routine [5]", "DOC"]],
    ];
    for (let i = 0; i < 6; i++) {
      for (let j = 0; j < 2; j++) {
        const [txt, k] = cards[i][j];
        const y = 3.45 + j * 1.25;
        s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: X(i), y, w: colW, h: 1.15, rectRadius: 0.06, fill: { color: C.background1 }, line: { color: k === "HYP" ? HEX.accent3 : HEX.accent6, width: k === "HYP" ? 1.5 : 1, dashType: k === "HYP" ? "dash" : "solid" }, objectName: `Failure point ${i + 1}.${j + 1}` });
        s.addText(txt, { x: X(i) + 0.1, y: y + 0.07, w: colW - 0.2, h: 0.78, fontSize: 11, color: i === 0 ? C.accent5 : C.text1, margin: 0, valign: "top", isTextBox: true });
        tag(s, k, X(i) + 0.1, y + 0.85);
      }
    }
    tag(s, "HYP", 0.6, 6.12);
    s.addText("The field evidence comes from short, local flows (markets 25–30 km away, Madhya Pradesh tomato) [3]. Whether these failure points grow on long inter-state hauls has not been tested.", { x: 2.4, y: 6.04, w: 10.33, h: 0.42, fontSize: 11.5, italic: true, color: C.text2, margin: 0, valign: "middle", isTextBox: true });
    source(s, "Sources: [1] NABCONS 2022, Annexure-II via PIB (1 Aug 2025); [3] Lamba, Singh & Anand, WRI India (2024), Tomato trail, Madhya Pradesh field study; [5] Roy et al., RBI WPS 08/2024.");
    s.addNotes("This is the existing process, not anything we propose. Walk left to right. The shaded band is our focus: from the assembly mandi to market entry. Nearly every failure point here comes from one measured field study, WRI India's 2024 tomato study in Madhya Pradesh: heat and vibration in transit, delays from permits, traffic and breakdowns, waiting outside the market, no storage, and packing in polythene bags. The dashed card is our hypothesis: that destinations are chosen without sight of conditions at other markets. Be honest about the limit: WRI studied local markets 25 to 30 km away. The RBI value-chain study shows that long inter-state hauls are routine, since Delhi gets tomatoes year-round from different states. How these failure points scale with distance is still an open question.");
  }

  // =====================================================================
  // 4. SIGNIFICANCE
  // =====================================================================
  pres.addSection({ title: "Evidence and people" });
  {
    const s = content("03  ·  HOW SIGNIFICANT IS IT?", "Fruit and vegetables lose 3–6× more than grains at the market stage", "Evidence and people");
    const labels = ["Wheat", "Paddy", "Potato", "Onion", "Banana", "Mango", "Tomato", "Guava"];
    s.addChart(pres.charts.BAR, [
      { name: "Farm operations", labels, values: [3.61, 4.16, 5.10, 5.31, 5.17, 6.03, 8.37, 11.59] },
      { name: "Market level (incl. transport, wholesale, retail)", labels, values: [0.56, 0.61, 0.86, 1.96, 2.40, 2.50, 3.25, 3.46] },
    ], {
      x: 0.6, y: 1.72, w: 7.5, h: 4.8, barDir: "col", barGrouping: "clustered", barGapWidthPct: 60,
      chartColors: [HEX.accent6, HEX.accent4],
      showTitle: true, title: "Post-harvest loss by stage, % of production (NABCONS, ref. 2020–22)", titleFontSize: 12, titleColor: HEX.dk2, titleFontFace: "+mn-lt",
      showLegend: true, legendPos: "b", legendFontSize: 11, legendFontFace: "+mn-lt", legendColor: HEX.dk1,
      showValue: true, dataLabelPosition: "outEnd", dataLabelFontSize: 9, dataLabelColor: HEX.dk1, dataLabelFontFace: "+mn-lt", dataLabelFormatCode: "0.0#",
      catAxisLabelColor: HEX.dk1, catAxisLabelFontSize: 11, catAxisLabelFontFace: "+mn-lt",
      valAxisLabelColor: HEX.accent5, valAxisLabelFontSize: 10, valAxisLabelFontFace: "+mn-lt", valAxisMinVal: 0, valAxisMaxVal: 13, valAxisMajorUnit: 2,
      showValAxisTitle: true, valAxisTitle: "% of production lost", valAxisTitleFontSize: 10, valAxisTitleColor: HEX.accent5, valAxisTitleFontFace: "+mn-lt",
      valGridLine: { color: "E3E8EB", size: 0.5 }, catGridLine: { style: "none" },
      objectName: "Chart loss by stage",
    });
    // bracket labels
    s.addText("Grains", { x: 1.25, y: 1.98, w: 1.4, h: 0.25, fontSize: 10, bold: true, color: C.accent5, align: "center", margin: 0, isTextBox: true });
    s.addText("Perishables", { x: 3.6, y: 1.98, w: 4.2, h: 0.25, fontSize: 10, bold: true, color: C.accent4, align: "center", margin: 0, isTextBox: true });

    card(s, 8.4, 1.72, 4.33, 1.45);
    s.addText("19.3 Mt", { x: 8.6, y: 1.8, w: 4, h: 0.62, fontFace: THEME.headFontFace, fontSize: 34, bold: true, color: C.accent4, margin: 0, isTextBox: true });
    s.addText("fruit (7.36 Mt) + vegetables (11.97 Mt) lost a year, all stages farm to retail [1]", { x: 8.6, y: 2.45, w: 3.95, h: 0.65, fontSize: 12, color: C.text1, margin: 0, valign: "top", isTextBox: true });
    card(s, 8.4, 3.32, 4.33, 1.45);
    s.addText("₹1.53 lakh crore", { x: 8.6, y: 3.4, w: 4, h: 0.62, fontFace: THEME.headFontFace, fontSize: 28, bold: true, color: C.text2, margin: 0, isTextBox: true });
    s.addText("annual value of post-harvest loss across all 54 commodities studied, not F&V alone (2020–21 production, 3-yr avg prices) [1]", { x: 8.6, y: 4.02, w: 3.95, h: 0.72, fontSize: 11.5, color: C.text1, margin: 0, valign: "top", isTextBox: true });
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 8.4, y: 4.92, w: 4.33, h: 1.6, rectRadius: 0.08, fill: { color: C.background1 }, line: { color: HEX.dk2, width: 1 }, objectName: "Caution box" });
    tag(s, "INT", 8.58, 5.04);
    s.addText("Read with care: “market level” bundles transport, wholesale, retail and processing. No transport-only share is published here, so these figures bound the problem; they do not measure transit loss.", { x: 8.58, y: 5.33, w: 4.0, h: 1.15, fontSize: 11.5, color: C.text1, margin: 0, valign: "top", isTextBox: true });
    source(s, "[1] NABCONS (2022) for MoFPI, as tabled in Rajya Sabha reply, PIB release 2151371 (1 Aug 2025), Annexure-II Tables 1–2. Earlier ICAR-CIPHET (2015) estimate [2]: ₹92,651 crore at 2014 prices. Methods and base years differ, so the two are not a trend.");
    s.addNotes("This is our strongest official evidence. The chart is from the NABCONS study for the Ministry of Food Processing Industries, the latest national loss study (reference period 2020-22). Look at the red bars, the market-level losses: wheat and paddy lose about 0.6 percent after leaving the farm; tomato 3.25 percent, guava 3.46 percent. That is 3 to 6 times more. Two cautions that show we read it properly: first, 'market level' includes transport, wholesale, retail and processing together, so we cannot say how much of it happens on the truck. Second, the 1.53 lakh crore figure covers all 54 commodities, not only fruit and vegetables. We also do not compare it with the older CIPHET estimate as a trend, because the methods differ.");
  }

  // =====================================================================
  // 5. STAKEHOLDERS
  // =====================================================================
  {
    const s = content("04  ·  WHO IS AFFECTED?", "The dispatcher decides the journey; the farmer often pays for it", "Evidence and people");
    // primary
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.6, y: 1.72, w: 4.35, h: 4.08, rectRadius: 0.08, fill: { color: C.text2 }, line: { type: "none" }, objectName: "Primary user card" });
    s.addText("PRIMARY USER", { shape: pres.shapes.ROUNDED_RECTANGLE, rectRadius: 0.12, x: 0.85, y: 1.95, w: 1.45, h: 0.27, fill: { color: C.accent2 }, color: C.text2, fontSize: 9.5, bold: true, charSpacing: 1, align: "center", valign: "middle", margin: 0, isTextBox: true });
    await iconCircle(s, fa.FaUserTie, 3.95, 1.92, 0.75, C.accent1, "Dispatcher");
    s.addText("The dispatcher", { x: 0.85, y: 2.35, w: 3.2, h: 0.5, fontFace: THEME.headFontFace, fontSize: 22, bold: true, color: C.background1, margin: 0, isTextBox: true });
    s.addText("Commission agent, trader or FPO marketing lead at the assembly mandi", { x: 0.85, y: 2.85, w: 3.85, h: 0.55, fontSize: 12.5, italic: true, color: C.accent6, margin: 0, valign: "top", isTextBox: true });
    s.addText("Chooses the destination, timing and packing for a load they cannot observe once it leaves. Field evidence shows these wholesale-level choices of packaging and destination distance shape shelf life [3].", { x: 0.85, y: 3.45, w: 3.85, h: 1.25, fontSize: 13, color: C.background1, margin: 0, valign: "top", isTextBox: true });
    s.addText([{ text: "Why primary: ", options: { bold: true } }, { text: "the difficulty starts at this decision point, and it is narrow enough to study directly." }], { x: 0.85, y: 4.85, w: 3.85, h: 0.8, fontSize: 12, color: C.accent2, margin: 0, valign: "top", isTextBox: true });

    const sec = [
      [fa.FaSeedling, "Farmer / FPO member", "Damaged lots sell for less, and that loss is borne mostly by the farmer [3]. Farmers get about 33% of the Delhi consumer price for tomato [5]."],
      [fa.FaTruckMoving, "Transporter / driver", "Deals with heat, rough roads, permit checks, waiting at market gates and breakdowns, in trucks without refrigeration [3]."],
      [fa.FaStore, "Receiving wholesaler / retailer", "No storage on site, so stock must sell the same day. In the study, 12% of tomatoes were wasted at retail and 11% sold as Grade II at about half price [3]."],
      [fa.FaShoppingBasket, "Consumer", "Perishability and short crop cycles make tomato, onion and potato prices swing sharply [5]."],
    ];
    const cx = [5.25, 9.08], cy = [2.02, 3.97];
    for (let i = 0; i < 4; i++) {
      const x = cx[i % 2], y = cy[Math.floor(i / 2)];
      card(s, x, y, 3.65, 1.83, C.background2, "Stakeholder " + sec[i][1]);
      await iconCircle(s, sec[i][0], x + 0.18, y + 0.18, 0.5, C.accent5, sec[i][1]);
      s.addText(sec[i][1], { x: x + 0.8, y: y + 0.18, w: 2.75, h: 0.5, fontSize: 14, bold: true, color: C.text2, margin: 0, valign: "middle", isTextBox: true });
      s.addText(sec[i][2], { x: x + 0.18, y: y + 0.75, w: 3.32, h: 1.02, fontSize: 11.5, color: C.text1, margin: 0, valign: "top", isTextBox: true });
    }
    s.addText("SECONDARY STAKEHOLDERS: affected by the outcome", { x: 5.25, y: 1.72, w: 7.48, h: 0.26, fontSize: 9.5, bold: true, color: C.accent5, charSpacing: 1, margin: 0, isTextBox: true });
    // influencers
    s.addText("SHAPE THE CONDITIONS", { x: 0.6, y: 6.0, w: 2.1, h: 0.42, fontSize: 9.5, bold: true, color: C.accent5, charSpacing: 1, margin: 0, valign: "middle", isTextBox: true });
    const inf = ["APMC boards & state governments", "e-NAM / Ministry of Agriculture", "MoFPI & NCCD (cold chain)", "Permits, roads & checkpoints"];
    let ix = 2.75;
    const iw = [2.6, 2.45, 2.2, 2.2];
    inf.forEach((t, i) => {
      s.addText(t, { shape: pres.shapes.ROUNDED_RECTANGLE, rectRadius: 0.18, x: ix, y: 6.02, w: iw[i], h: 0.38, fill: { color: C.background1 }, line: { color: HEX.accent5, width: 0.75 }, fontSize: 11, color: C.text2, align: "center", valign: "middle", margin: 0, isTextBox: true, objectName: "Influencer " + t });
      ix += iw[i] + 0.12;
    });
    source(s, "Stakeholder difficulties come from published studies; we have not yet run our own interviews. [3] WRI India 2024 (MP tomato chain); [5] RBI WPS 08/2024 (Delhi value chain).");
    s.addNotes("One logistics difficulty lands differently on each person. The dispatcher, our primary user, makes the decision: where to send, when, and how packed. WRI found that these wholesale-level choices of packaging and destination distance shape shelf life. The farmer usually bears the economic loss when produce arrives damaged, and receives about a third of the consumer price for tomato (RBI). The driver handles heat, rough roads, permit and market-gate waits. The receiving trader has no storage, so they sell the same day or at distress prices. The consumer sees it as price volatility. The bottom row lists actors who shape the conditions without facing the problem day to day. Say clearly: all of this comes from published studies. Talking to dispatchers ourselves is the obvious next step in discovery.");
  }

  // =====================================================================
  // 6. CAUSES
  // =====================================================================
  pres.addSection({ title: "Causes and current approaches" });
  {
    const s = content("05  ·  WHY DOES IT HAPPEN?", "Why it persists: produce moves warm through an unmeasured chain", "Causes and current approaches");
    legend(s);
    const cols = [
      ["UNDERLYING CONDITIONS", C.text2, [
        ["Cold chain built for storage, not movement: an 85% shortfall in reefer vehicles and 99.6% in pack-houses (2014–15) [4]", "DOC"],
        ["A fragmented chain with many intermediaries; decisions are split across actors [5]", "DOC"],
        ["Transit conditions and outcomes are not recorded in any public dataset (slide 9)", "DOC"],
        ["Dispatchers lack a timely view of conditions at destination and on the way", "HYP"],
      ]],
      ["PROXIMATE CAUSES", C.accent1, [
        ["Heat exposure: perishables deteriorate 2–3× faster for every 10°C rise [6]", "DOC"],
        ["Delay: inter-state permits, waiting outside markets, traffic, breakdowns [3]", "DOC"],
        ["Mechanical damage: vibration, poor roads, polythene bags, overfilled crates [3]", "DOC"],
        ["Arrival mismatch: produce reaches a glutted market with no storage to wait in [3][5]", "DOC"],
      ]],
      ["OBSERVABLE SYMPTOMS", C.accent4, [
        ["Produce downgraded on arrival (Grade II sold at about half price) [3]", "DOC"],
        ["Distress and same-day selling at markets and retail [3]", "DOC"],
        ["Physical wastage at the market stage: 2–3.5% for most F&V [1]", "DOC"],
        ["Sharp price swings across seasons and markets [5]", "DOC"],
      ]],
    ];
    const W = 3.75, xs = [0.6, 4.79, 8.98];
    cols.forEach(([head, color, items], c) => {
      s.addText(head, { shape: pres.shapes.RECTANGLE, x: xs[c], y: 1.72, w: W, h: 0.42, fill: { color }, color: C.background1, fontSize: 12, bold: true, charSpacing: 2, align: "center", valign: "middle", margin: 0, isTextBox: true });
      items.forEach(([t, k], i) => {
        const y = 2.25 + i * 1.04;
        s.addShape(pres.shapes.RECTANGLE, { x: xs[c], y, w: W, h: 0.96, fill: { color: k === "HYP" ? "FBF3DF" : C.background2 }, line: k === "HYP" ? { color: HEX.accent3, width: 1.25, dashType: "dash" } : { type: "none" }, objectName: `${head} ${i + 1}` });
        s.addText(t, { x: xs[c] + 0.14, y: y + 0.06, w: W - 0.28, h: 0.62, fontSize: 11.5, color: C.text1, margin: 0, valign: "top", isTextBox: true });
        tag(s, k, xs[c] + 0.14, y + 0.69);
      });
      if (c < 2) s.addShape(pres.shapes.RIGHT_ARROW, { x: xs[c] + W + 0.08, y: 3.85, w: 0.28, h: 0.5, fill: { color: C.accent5 }, line: { type: "none" }, objectName: "Cause arrow " + c });
    });
    source(s, "How much each cause contributes in transit has not been quantified in published Indian data. Consequences are on slide 8. Sources: [1] NABCONS 2022; [3] WRI India 2024; [4] NCCD 2015; [5] RBI 2024; [6] Kader & Rolle, FAO AGS Bulletin 152 (2004).");
    s.addNotes("Read right to left. On the right are what you can see at the market: downgrades, distress sales, wastage, price swings. In the middle are the proximate causes, all documented: heat (FAO's rule of thumb is that deterioration is 2 to 3 times faster for every 10 degrees), delay, mechanical damage, and arriving into a glut with nowhere to store. On the left are the underlying conditions that keep the problem going. India's cold-chain gap is not mainly in storage, which was about 9 percent short; it is in reefer vehicles (85 percent short) and pack-houses (99.6 percent short), per NCCD's 2015 assessment. The chain is fragmented. And no one records what happens in transit. The dashed card, that dispatchers lack a timely view of conditions, is our hypothesis. We have not tested it.");
  }

  // =====================================================================
  // 7. EXISTING APPROACHES
  // =====================================================================
  {
    const s = content("06  ·  WHAT IS BEING DONE TODAY?", "Today's efforts address storage, prices and trucks more than the trip", "Causes and current approaches");
    const H = (t) => ({ text: t, options: { bold: true, color: C.background1, fill: { color: C.text2 }, fontSize: 12, valign: "middle" } });
    const ev = (t, k) => ({ text: t, options: { bold: true, color: k === "DOC" ? C.accent1 : k === "INT" ? C.text2 : "9A6D00" } });
    const rows = [
      ["Cold-chain infrastructure (PMKSY Cold Chain scheme; NCCD planning)", "Funds cold stores, pack-houses, reefer transport", "Heat exposure, holding", "Shortfall concentrated in movement: reefers 85%, pack-houses 99.6% (2014–15); storage skewed to bulk, single-commodity stores such as potato", ev("Documented [4]", "DOC")],
      ["Digital market information & trading (Agmarknet; e-NAM, 1,656 mandis by Mar 2026)", "Daily arrivals and prices; online bidding across mandis", "Price discovery, buyer reach", "Records what arrived and at what price, not trip time or arrival condition. Government calls logistics “a major hurdle” for inter-mandi trade", ev("Documented [7][8]; dataset scope: interpretation [9]", "DOC")],
      ["Kisan Rath app (MoA&FW, 2020)", "Matches consignors with trucks and aggregators", "Truck availability", "Downloads fell over time; over half of users rely on local transport outside the app", ev("Documented [10]", "DOC")],
      ["Operation Greens “TOP to TOTAL”: 50% freight subsidy on Kisan Rail", "Subsidised moving notified F&V from surplus to consumption areas", "Cost of long hauls", "Time-bound pilot (Oct 2020–Mar 2021), rail-only; current status not verified", ev("Documented [11]", "DOC")],
      ["Navigation & route-optimisation tools (e.g. Google Maps, Route Optimization API)", "Traffic-aware ETAs; time windows, vehicle capacity, cost per km/hour", "Travel time, fleet planning", "No built-in model of produce quality decay in public documentation; shelf life can only be approximated as a time window", ev("Interpretation of public docs [12]; validate", "INT")],
      ["Research on perishable-goods routing", "Models quality decay inside vehicle-routing problems", "Planning under perishability", "Review of 65 papers: dynamic, quality-aware routing still open; no agreed decay model; mostly cold-chain settings", ev("Documented [13]; India-ambient gap: to confirm", "INT")],
    ];
    const body = rows.map((r, i) => r.map((c) => {
      const base = { fontSize: 11, color: C.text1, valign: "middle", fill: { color: i % 2 ? C.background2 : C.background1 } };
      if (typeof c === "string") return { text: c, options: base };
      return { text: c.text, options: { ...base, ...c.options } };
    }));
    body.forEach((r) => (r[0].options = { ...r[0].options, bold: true, color: C.text2 }));
    s.addTable([[H("Approach"), H("What it does"), H("Addresses"), H("Gap that remains within our scope"), H("Evidence")], ...body], {
      x: 0.6, y: 1.68, w: 12.13, colW: [2.55, 2.35, 1.45, 4.08, 1.7], rowH: [0.36, 0.76, 0.76, 0.66, 0.7, 0.76, 0.76],
      border: { type: "solid", pt: 0.75, color: HEX.accent6 }, margin: [0.04, 0.08, 0.04, 0.08], autoPage: false,
      objectName: "Existing approaches matrix",
    });
    source(s, "None of these is ineffective. Each targets a different part of the problem. [4] NCCD 2015; [7] Rajya Sabha reply, 7 Feb 2025; [8] PIB, Apr 2026; [9] agmarknet.gov.in; [10] Shalendra et al. 2021 (MANAGE); [11] MoFPI / Lok Sabha reply on Operation Greens; [12] Google Route Optimization API docs; [13] Awad, Ndiaye & Osman 2021.");
    s.addNotes("Be fair here. These approaches are not failures; each does something real. Cold-chain schemes address heat and storage, but NCCD found the shortfall is mainly in movement: reefers and pack-houses. Agmarknet and e-NAM give prices and arrivals and enable online trade, but they record what arrived, not how the trip went. The government itself told Parliament in February 2025 that logistics is a major hurdle for inter-mandi trade on e-NAM. Kisan Rath tackles finding a truck, but MANAGE found falling use. The Kisan Rail freight subsidy cut the cost of long hauls, but it was a time-bound pilot. General routing tools optimise time, distance, capacity and time windows; we found no built-in produce-quality model in their public documentation, but that is our reading and should be checked. Academic work on perishable routing exists, and a 2021 review of 65 papers says dynamic, quality-aware routing is still open. Whether India's non-refrigerated mandi-to-market setting is under-studied needs a proper literature review before we claim it.");
  }

  // =====================================================================
  // 8. CONSEQUENCES
  // =====================================================================
  pres.addSection({ title: "Consequences and gaps" });
  {
    const s = content("07  ·  WHAT ARE THE CONSEQUENCES?", "Costs fall on farm income, market quality and consumer prices", "Consequences and gaps");
    const items = [
      [fa.FaSeedling, "FARMER", "~33%", "farmers' share of the Delhi consumer price for tomato (onion ~36%, potato ~37%). The rest covers transport, fees, losses and margins [5]"],
      [fa.FaBalanceScale, "TRADER", "5–10%", "weight loss traders absorb on onion: about 5% for the rabi crop, about 10% for kharif [5]"],
      [fa.FaStore, "RECEIVING MARKET", "12%", "of tomatoes wasted at retail by day's end in the MP study, with another 11% sold as Grade II at about half price [3]"],
      [fa.FaShoppingBasket, "CONSUMER", "Volatile", "TOP prices swing sharply, driven partly by perishability and short seasonal cycles, and feed into food and headline inflation [5]"],
    ];
    const W = 2.845;
    for (let i = 0; i < 4; i++) {
      const x = 0.6 + i * (W + 0.25);
      card(s, x, 1.72, W, 3.6, C.background2, "Consequence " + items[i][1]);
      await iconCircle(s, items[i][0], x + 0.22, 1.92, 0.6, C.accent4, items[i][1]);
      s.addText(items[i][1], { x: x + 0.95, y: 1.92, w: W - 1.05, h: 0.6, fontSize: 11, bold: true, charSpacing: 1, color: C.accent5, margin: 0, valign: "middle", isTextBox: true });
      s.addText(items[i][2], { x: x + 0.22, y: 2.65, w: W - 0.4, h: 0.75, fontFace: THEME.headFontFace, fontSize: 34, bold: true, color: C.text2, margin: 0, valign: "middle", isTextBox: true });
      s.addText(items[i][3], { x: x + 0.22, y: 3.45, w: W - 0.42, h: 1.8, fontSize: 12, color: C.text1, margin: 0, valign: "top", isTextBox: true });
    }
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.6, y: 5.5, w: 6.6, h: 0.98, rectRadius: 0.08, fill: { color: C.background1 }, line: { color: HEX.accent6, width: 1 }, objectName: "Food system box" });
    await iconCircle(s, fa.FaLeaf, 0.78, 5.7, 0.55, C.accent1, "Food system");
    s.addText([{ text: "Food system: ", options: { bold: true, color: C.accent1 } }, { text: "19.3 Mt of F&V lost each year across all stages [1]. In the MP study districts, tomato lost at wholesale and retail adds about 6,824 t CO₂e a year from landfill [3]." }], { x: 1.5, y: 5.55, w: 5.6, h: 0.9, fontSize: 11.5, color: C.text1, margin: 0, valign: "middle", isTextBox: true });
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 7.45, y: 5.5, w: 5.28, h: 0.98, rectRadius: 0.08, fill: { color: C.background1 }, line: { color: HEX.dk2, width: 1 }, objectName: "Interpretation box" });
    tag(s, "INT", 7.62, 5.6);
    s.addText("These costs build up across the whole chain. With current data, the share that starts in transit cannot be separated out. That is a gap in itself.", { x: 7.62, y: 5.86, w: 4.98, h: 0.58, fontSize: 11.5, color: C.text1, margin: 0, valign: "top", isTextBox: true });
    source(s, "[1] NABCONS 2022 via PIB 2025; [3] WRI India 2024, Madhya Pradesh tomato chain (direct measurement, 2020–21 production base); [5] Roy et al., RBI WPS (DEPR) 08/2024, value-chain estimates for Delhi.");
    s.addNotes("Tie each number back to a person from slide 5. Farmers get about a third of what the consumer pays for tomato. That gap covers transport, fees, losses and margins, so it is not all waste, but losses are part of it. Traders absorb 5 to 10 percent weight loss on onion. At the receiving market, WRI measured 12 percent tomato waste at retail plus 11 percent downgraded and sold at about half price. Consumers feel it as price swings. RBI notes that tomato, onion and potato move headline inflation despite their small CPI weight. The box on the right is the honest bridge to the next slide: these consequences pile up along the whole chain, and with today's data nobody can say what share starts on the truck.");
  }

  // =====================================================================
  // 9. GAPS
  // =====================================================================
  {
    const s = content("08  ·  WHAT REMAINS INADEQUATELY UNDERSTOOD?", "Three distinct gaps: in data, in research and in everyday practice", "Consequences and gaps");
    const cols = [
      ["DATA GAP", "verified", C.accent1, [
        "Fresh F&V need no GST e-way bill (CGST Rule 138(14)(e)), so India's main digital freight record largely misses these trips [14]",
        "Agmarknet and e-NAM record arrivals, prices and trades, not trip duration, route or condition on arrival [8][9]",
        "We found no public trip-level spoilage or rerouting-decision dataset [15]",
        "Indian loss studies rely more on perception surveys than on direct measurement [3]",
      ]],
      ["RESEARCH GAP", "partly established", C.text2, [
        "Dynamic, quality-aware routing is still an open research area, with no agreed decay model [13]",
        "Most quality-decay work assumes refrigerated settings; India's ambient mandi-to-market flows look thinly studied (to confirm by systematic review)",
        "Loss studies split losses into farm and market stages, not transit vs waiting vs handling [1]",
      ]],
      ["PRACTICE GAP", "hypothesis", C.accent3, [
        "How dispatchers choose destination and timing today, and what information they use: we found no published evidence",
        "Whether problems en route (delay, heat, a glut at destination) are noticed and acted on after dispatch",
        "Which signals (prices elsewhere, weather, road delays) dispatchers can actually access when they decide",
      ]],
    ];
    const W = 3.75, xs = [0.6, 4.79, 8.98];
    cols.forEach(([h, sub, color, items], c) => {
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: xs[c], y: 1.72, w: W, h: 3.15, rectRadius: 0.08, fill: { color: C.background1 }, line: { color: c === 2 ? HEX.accent3 : c === 0 ? HEX.accent1 : HEX.dk2, width: 1.25, dashType: c === 2 ? "dash" : "solid" }, objectName: h + " column" });
      s.addText([{ text: h, options: { bold: true, color: c === 2 ? C.text1 : C.background1 } }, { text: "  ·  " + sub, options: { color: c === 2 ? C.text1 : C.background1 } }], { shape: pres.shapes.RECTANGLE, x: xs[c], y: 1.72, w: W, h: 0.42, fill: { color }, fontSize: 12, charSpacing: 1, align: "center", valign: "middle", margin: 0, isTextBox: true });
      s.addText(items.map((t, i) => ({ text: t, options: { bullet: { indent: 12 }, breakLine: i < items.length - 1 } })), { x: xs[c] + 0.15, y: 2.25, w: W - 0.3, h: 2.55, fontSize: 11.5, color: C.text1, margin: 0, valign: "top", paraSpaceAfter: 5, isTextBox: true });
    });
    // open questions
    card(s, 0.6, 5.02, 8.0, 1.48, C.background2, "Open questions");
    s.addText("OPEN QUESTIONS THIS BRIEF RAISES", { x: 0.78, y: 5.1, w: 6, h: 0.28, fontSize: 10, bold: true, charSpacing: 1, color: C.accent1, margin: 0, isTextBox: true });
    const qs = ["1  What share of market-level loss arises in transit, in waiting, and in handling?", "2  How does it vary with distance, season (summer heat, monsoon) and region?", "3  How often do loads arrive into a glut, and could that have been known at dispatch?", "4  Which crops are most sensitive to delay, and which to heat?"];
    qs.forEach((q, i) => s.addText(q, { x: 0.78 + (i % 2) * 3.95, y: 5.42 + Math.floor(i / 2) * 0.52, w: 3.8, h: 0.5, fontSize: 11, color: C.text1, margin: 0, valign: "top", isTextBox: true }));
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 8.85, y: 5.02, w: 3.88, h: 1.48, rectRadius: 0.08, fill: { color: C.text2 }, line: { type: "none" }, objectName: "Caveat box" });
    s.addText("Scarce data shows the problem is under-measured, not that it is large. Its size in transit has to be established, not assumed.", { x: 9.05, y: 5.1, w: 3.5, h: 1.32, fontFace: THEME.headFontFace, fontSize: 13.5, italic: true, color: C.background1, margin: 0, valign: "middle", isTextBox: true });
    source(s, "[1] NABCONS 2022; [3] WRI India 2024; [8] PIB 2026; [9] agmarknet.gov.in; [13] Awad et al. 2021; [14] CGST Rules 2017, r.138(14)(e) with Notif. 2/2017-CT(Rate) Schedule (fresh fruits & vegetables exempt); [15] team research blueprint, data-availability audit (internal).");
    s.addNotes("This slide keeps three gaps apart. A data gap: fresh fruit and vegetables are GST-exempt, so they need no e-way bill. That means the main digital record of freight movement in India largely misses these trips. Agmarknet and e-NAM show arrivals and prices, not journeys. We found no public trip-level spoilage or rerouting data. A research gap: a 2021 review of 65 papers calls dynamic, quality-aware routing an open area, and most work assumes refrigerated chains. We think India's ambient setting is thinly studied, but we will only claim that after a systematic review. A practice gap: we found no published evidence on how dispatchers actually decide today. That is a hypothesis for fieldwork. Then read the caveat aloud. A lack of data does not prove the problem is big; it means the size has to be measured.");
  }

  // =====================================================================
  // 10. WORTH SOLVING
  // =====================================================================
  {
    const s = content("09  ·  WHY IT IS WORTH SOLVING", "Why this problem deserves investigation now", "Consequences and gaps");
    const tiles = [
      [fa.FaExclamationCircle, "It is meaningful", "F&V lose 19.3 Mt a year, and three to six times more than grains at the market stage [1]; farmers keep about a third of the consumer price [5]."],
      [fa.FaUsers, "Many gain from understanding it", "Farmers and FPOs who absorb downgrades, the dispatchers who choose markets, receiving traders, and agencies planning cold-chain and market investment [4]."],
      [fa.FaSearch, "The gaps are real", "Transit outcomes are not in public data, quality-aware dynamic routing is an open research question, and we found no published study of how dispatchers decide (slide 9)."],
      [fa.FaCrosshairs, "It is specific and researchable", "Bounded by crop (highly perishable F&V), leg (mandi to receiving market) and mode (ambient road), and testable with public market data plus field measurement."],
    ];
    const W = 2.845;
    for (let i = 0; i < 4; i++) {
      const x = 0.6 + i * (W + 0.25);
      card(s, x, 1.72, W, 2.95, C.background2, "Reason " + (i + 1));
      await iconCircle(s, tiles[i][0], x + 0.22, 1.92, 0.58, C.accent1, tiles[i][1]);
      s.addText(tiles[i][1], { x: x + 0.22, y: 2.6, w: W - 0.4, h: 0.62, fontSize: 15, bold: true, color: C.text2, margin: 0, valign: "top", isTextBox: true });
      s.addText(tiles[i][2], { x: x + 0.22, y: 3.28, w: W - 0.42, h: 1.35, fontSize: 11.5, color: C.text1, margin: 0, valign: "top", isTextBox: true });
    }
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.6, y: 4.88, w: 12.13, h: 1.62, rectRadius: 0.08, fill: { color: C.text2 }, line: { type: "none" }, objectName: "Closing statement" });
    s.addText("THE PROBLEM IN ONE SENTENCE", { x: 0.9, y: 5.0, w: 6, h: 0.28, fontSize: 10, bold: true, charSpacing: 2, color: C.accent2, margin: 0, isTextBox: true });
    s.addText("In India, perishable fruit and vegetables lose value on the road between mandi and market: a stretch that is rarely refrigerated, rarely measured, and little studied from the point of view of the people who dispatch the load.", { x: 0.9, y: 5.3, w: 11.55, h: 1.1, fontFace: THEME.headFontFace, fontSize: 18, italic: true, color: C.background1, margin: 0, valign: "middle", isTextBox: true });
    source(s, "[1] NABCONS 2022 via PIB 2025; [4] NCCD 2015; [5] RBI WPS 08/2024. Our next discovery step is to check the primary-user hypothesis directly with dispatchers.");
    s.addNotes("Bring it together. It matters: 19.3 million tonnes lost a year, and fruit and vegetables lose 3 to 6 times more than grain once off the farm. Farmers keep only a third of the price. Many people gain from understanding it better, including the agencies deciding where cold-chain money goes. The gaps are real and we kept them separate: data, research and practice. And the problem is narrow enough to study: one crop group, one leg, one mode. Finish with the sentence on screen, and say it word for word. Do not mention any solution. If asked what comes next, say: talking to dispatchers to test our hypothesis.");
  }

  // =====================================================================
  // 11–12. REFERENCES
  // =====================================================================
  pres.addSection({ title: "References" });
  const refs = [
    ["[1]", "NABARD Consultancy Services (NABCONS) for Ministry of Food Processing Industries (2022). Study to Determine Post-Harvest Losses of Agri Produces in India (ref. period 2020–22). Figures as tabled in Rajya Sabha, PIB release ID 2151371, 1 Aug 2025, Annexures I–II.", "https://www.pib.gov.in/PressReleasePage.aspx?PRID=2151371", "Slides 1, 3, 4, 6, 8, 9, 10"],
    ["[2]", "Jha, S.N. et al. / ICAR-CIPHET (2015). Assessment of Quantitative Harvest and Post-Harvest Losses of Major Crops and Commodities in India. Total loss value ₹92,651 crore, as reported in a Lok Sabha reply.", "https://eparlib.nic.in/bitstream/123456789/706362/1/56899.pdf", "Slide 4 (footnote)"],
    ["[3]", "Lamba, S., Singh, R. & Anand, S. (2024). Tomato Trail: Tracking Food Loss and Food Waste in Madhya Pradesh. Working Paper, WRI India, Sept 2024.", "https://wri-india.org/sites/default/files/Tomato-trail-Tracking-food-loss-food-waste-Madhya-Pradesh.pdf", "Slides 3, 5, 6, 8, 9"],
    ["[4]", "National Centre for Cold-chain Development & NABCONS (2015). All India Cold-chain Infrastructure Capacity (Assessment of Status & Gap). Requirement vs created, 2014–15.", "https://nccd.gov.in/uploads/All_India_Cold_Chain_Infrastructure_2015_5da1279baa.pdf", "Slides 2, 6, 7, 10"],
    ["[5]", "Roy, R., Gupta, S., Wardhan, H., Sarkar, S., Tewari, S., Bansal, R., Bhatia, S. & Gulati, A. (2024). Vegetables Inflation in India: A Study of Tomato, Onion and Potato (TOP). RBI Working Paper Series (DEPR) No. 08/2024.", "https://rbi.org.in/Scripts/PublicationsView.aspx?id=22723", "Slides 3, 5, 6, 8, 10"],
    ["[6]", "Kader, A.A. & Rolle, R.S. (2004). The Role of Post-Harvest Management in Assuring the Quality and Safety of Horticultural Produce. FAO Agricultural Services Bulletin 152, Section 3.2.", "https://www.fao.org/4/y5431e/y5431e04.htm", "Slide 6"],
    ["[7]", "Rajya Sabha (2025). Ministry of Agriculture & Farmers Welfare, reply to Question 267 on e-NAM, 7 Feb 2025 (inter-state trade; logistics as a hurdle; e-NAM 2.0).", "https://rsdebate.nic.in/bitstream/123456789/758227/1/PQ_267_07022025_S46_p1_p12.pdf", "Slide 7"],
    ["[8]", "Press Information Bureau (2026). e-NAM backgrounder, April 2026: 1,656 mandis in 23 states and 4 UTs onboarded.", "https://static.pib.gov.in/WriteReadData/specificdocs/documents/2026/apr/doc2026413845801.pdf", "Slides 7, 9"],
  ];
  const refs2 = [
    ["[9]", "Directorate of Marketing & Inspection, MoA&FW. AGMARKNET portal: daily commodity arrivals and prices reported by markets.", "https://agmarknet.gov.in", "Slides 7, 9"],
    ["[10]", "Shalendra, Kumar, R., Gummagolmath, K.C. & Angadi, S. (2021). Transportation in Agriculture: A Case of Kisan Rath App. Journal of Agricultural Extension Management (MANAGE).", "https://epubs.icar.org.in/index.php/JAEM/article/download/159460/62590/489185", "Slide 7"],
    ["[11]", "Ministry of Food Processing Industries (2020–21). Operation Greens “TOP to TOTAL”: 50% freight subsidy for notified fruits & vegetables on Kisan Rail. Lok Sabha Unstarred Q. 2423.", "https://eparlib.nic.in/bitstream/123456789/992164/1/AU2423.pdf", "Slide 7"],
    ["[12]", "Google Maps Platform (2025). Route Optimization API: parameter list and ShipmentModel reference (time windows, load demands, cost per hour/km).", "https://developers.google.com/maps/documentation/route-optimization/parameter-list", "Slide 7"],
    ["[13]", "Awad, M., Ndiaye, M. & Osman, A. (2021). Vehicle routing in cold food supply chain logistics: a literature review. The International Journal of Logistics Management, 32(2), 592–617.", "https://doi.org/10.1108/IJLM-02-2020-0092", "Slides 7, 9"],
    ["[14]", "Central Goods and Services Tax Rules, 2017, Rule 138(14)(e) (as substituted by Notification 12/2018-Central Tax) read with the Schedule to Notification 2/2017-Central Tax (Rate).", "https://www.gstzen.in/a/rule-138-central-goods-and-services-tax-rules-2017-cgst-rule-138-replaced-as-per-central-tax-notification-122018.html", "Slide 9"],
    ["[15]", "[Team name] (2026). Agricultural Supply Chain Research Blueprint: dataset inventory and data-availability classification (internal document).", "Internal, not published", "Slide 9"],
  ];
  const refSlide = (title, list, note) => {
    const s = content("REFERENCES", title, "References");
    let y = 1.68;
    const rowH = list.length > 7 ? 0.6 : 0.66;
    list.forEach(([n, t, url, used]) => {
      s.addText(n, { x: 0.6, y, w: 0.55, h: rowH - 0.06, fontSize: 11, bold: true, color: C.accent1, margin: 0, valign: "top", isTextBox: true });
      const runs = [{ text: t + " ", options: { color: C.text1 } }];
      if (url.startsWith("http")) runs.push({ text: url, options: { color: C.accent1, hyperlink: { url } } });
      else runs.push({ text: url, options: { color: C.accent5, italic: true } });
      s.addText(runs, { x: 1.15, y, w: 9.45, h: rowH - 0.06, fontSize: 10, margin: 0, valign: "top", isTextBox: true });
      s.addText(used, { x: 10.75, y, w: 1.98, h: rowH - 0.06, fontSize: 10, italic: true, color: C.accent5, margin: 0, valign: "top", isTextBox: true });
      y += rowH;
    });
    s.addText("USED ON", { x: 10.75, y: 1.42, w: 1.98, h: 0.24, fontSize: 9, bold: true, charSpacing: 1, color: C.accent5, margin: 0, isTextBox: true });
    if (note) source(s, note);
    return s;
  };
  const r1 = refSlide("Sources, numbered as cited on each slide (1/2)", refs, "All URLs were checked in October 2026. Parliamentary figures are as tabled on the date given. No stakeholder interviews, field visits or surveys of our own are reported in this deck.");
  r1.addNotes("Every number in the deck carries a bracketed number that maps here. If an evaluator asks where a figure comes from, point to the 'used on' column. The main sources are NABCONS 2022 (via the PIB annexure), WRI India 2024 (direct field measurement), NCCD 2015, and the RBI 2024 TOP working paper.");
  const r2 = refSlide("Sources, numbered as cited on each slide (2/2)", refs2, "[14] is our reading of the e-way bill rule; check it against the current CBIC text before relying on it operationally. [15] is our own planning document, cited for its data-availability audit, not as external evidence.");
  r2.addNotes("Be clear about two sources. Reference 14 is our interpretation of the GST e-way bill rule: fresh fruit and vegetables are in the exempt schedule, so no e-way bill is needed. Reference 15 is our own blueprint, cited only for its audit of which datasets exist.");

  await pres.writeFile({ fileName: OUT });
  await applyTheme(OUT, THEME);
  console.log("wrote", OUT);
})().catch((e) => { console.error(e); process.exit(1); });
