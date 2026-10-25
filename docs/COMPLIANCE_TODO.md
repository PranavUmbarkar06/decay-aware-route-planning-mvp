# Compliance TODO (needs qualified review: no legal conclusions are drawn here)

| Area | Why it matters here | What to get reviewed | Owner |
|---|---|---|---|
| Food donation (M5) | Lots donated to NGOs may be near the end of their shelf life. The app shows a model-based "safe window" with a margin, explicitly not a certification. | Applicable food-safety rules for surplus-food donation in India, labelling and handling duties, and who carries liability (sender, NGO, platform). Whether the "safe window" wording is acceptable. | Counsel / food-safety specialist |
| Personal data | Phone numbers, roles, locations and scan histories of identifiable people (farmers, drivers). | India's data-protection law obligations (notice, consent, purpose limitation, retention, deletion requests, breach handling) and whether the consent text in onboarding is sufficient. | Counsel |
| Data retention | Custody logs are append-only and tamper-evident; deletion requests may conflict with that. | A retention schedule and a lawful approach to erasure requests (e.g. pseudonymising actor ids while keeping hashes). | Counsel + engineering |
| Open data licences | OSM (ODbL: attribution + share-alike for derived databases such as nodes.csv/edges.csv), Open-Meteo (CC BY 4.0; free API non-commercial), Agmarknet (terms not found), UC Davis fact sheets (no copying; cited only), Census (terms not stated). | Confirm reuse terms before any public release or commercial use; attribution is already shown in the app footer. | Project owner |
| Agmarknet access | Report data is captcha-gated; only human-downloaded exports are used. | Whether redistributing derived arrival tables is permitted. | Project owner |
| Commodity market rules | Recommendations about destinations touch APMC trading. | Whether advice could conflict with APMC/e-NAM rules in Maharashtra. | Domain expert |
