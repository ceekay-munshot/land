# 📥 Drop circle-rate files here

Phase 1 (prices) needs the official **circle / DLC rate** for our pilot area.
It sits behind a captcha, so it's a **one-time manual grab** — we'll automate refreshes afterwards.

## How to get it (~2 minutes, from an India connection)
1. Open **https://igrsup.gov.in**
2. Go to the **circle-rate / valuation-list** section (Hindi: **"सर्किल रेट"** or **"मूल्यांकन सूची"**)
3. **District (जनपद):** choose **गौतम बुद्ध नगर** (Gautam Buddh Nagar)
4. **SRO office (उपनिबंधक कार्यालय):** choose **जेवर (Jewar)**
   *(later we'll also grab दादरी / Dadri and सदर / Sadar)*
5. Type the **captcha**, then open/**download the PDF** of the rate list

## How to hand it to me (pick whichever is easiest)
- **Best:** drag the PDF into this `data_in/` folder on github.com
  (*Add file → Upload files → drop it → Commit*), then tell me "done"
- **Or:** just send me the **agricultural (कृषि) rate** numbers for the Jewar area

Once it's here I parse it, put a real ₹ value on every parcel, **then** build the
Firecrawl auto-refresh so this never needs doing by hand again.
