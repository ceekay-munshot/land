---
name: dashboard-builder
description: Mandatory Munshot standards for building embedded dashboards. Use this skill EVERY time a task involves creating, building, generating, modifying, or reviewing a dashboard of any type (screener, sector monitor, heatmap, brand discounts tracker, document intelligence, portfolio/watchlist, company comparison). Defines the required 3-zone iframe layout, WidgetCard structure, design tokens, loading/empty/error states, Munshot Dashboard SDK auth integration, and the registered datasource registry. Read and follow it in full before writing any dashboard code.
---

# Dashboard Skill - Standards and Best Practices

This skill guide provides dashboard engineers with comprehensive standards, patterns, and best practices for building consistent, maintainable dashboards across the organization.

## UI Standards

These UI standards come from the Munshot frontend dashboard builder guide and are mandatory for embedded dashboards.

### Mandatory 3-Zone Layout

Every dashboard must use this exact iframe shell:

```text
Dashboard App
+-- Zone 1: Sticky Header Bar, height 48px
+-- Zone 2: Scrollable Content Area, flex: 1
+-- Zone 3: Optional Sticky Footer, height about 40px
```

Use this outer shell:

```css
.dashboard-shell {
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
  background: linear-gradient(to bottom, rgba(249, 250, 251, 0.8), #ffffff);
  font-family:
    system-ui,
    -apple-system,
    sans-serif;
  color: #111827;
}
```

Rules:

- The dashboard must fill the iframe with `height: 100vh`.
- The page itself must not scroll. Only Zone 2 scrolls.
- Do not create marketing pages, hero sections, or standalone navigation shells.
- Do not use a persistent left sidebar unless the host product explicitly provides one outside the iframe.

### Zone 1: Header Bar

The header is required and must always be sticky at the top.

```tsx
<header
  style={{
    position: "sticky",
    top: 0,
    zIndex: 10,
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "0 24px",
    height: 48,
    background: "rgba(255, 255, 255, 0.95)",
    backdropFilter: "blur(8px)",
    borderBottom: "1px solid #e5e7eb",
    flexShrink: 0,
  }}
>
  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
    <h1 style={{ fontSize: 15, fontWeight: 700, color: "#111827", margin: 0 }}>
      Dashboard Title
    </h1>
    {ticker && <TickerPill ticker={ticker} company={company} />}
  </div>
  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
    {/* view toggle, filter button, refresh, export */}
  </div>
</header>
```

Header rules:

- Height must be exactly `48px`.
- Background must be `rgba(255,255,255,0.95)`.
- Use `backdrop-filter: blur(8px)`.
- Bottom border must be `1px solid #e5e7eb`.
- Title must be `15px`, `700`, `#111827`.
- Show the active ticker pill only when a ticker is selected.
- Never put charts, tables, or large descriptions in the header.

Ticker pill style:

```tsx
<span
  style={{
    display: "inline-flex",
    alignItems: "center",
    gap: 6,
    padding: "2px 10px",
    background: "#eef2ff",
    color: "#4338ca",
    borderRadius: 99,
    fontSize: 12,
    fontWeight: 600,
    border: "1px solid #e0e7ff",
  }}
>
  <span
    style={{ width: 6, height: 6, background: "#6366f1", borderRadius: "50%" }}
  />
  {ticker}
  {company && (
    <span style={{ color: "#818cf8", fontWeight: 400 }}>- {company}</span>
  )}
</span>
```

### Zone 2: Scrollable Content Area

Zone 2 holds all dashboard content and must be the only scrolling area.

```tsx
<main
  style={{
    flex: 1,
    overflow: "auto",
    padding: "24px 32px",
  }}
>
  {/* filters, KPI widgets, charts, tables, source widgets */}
</main>
```

Use `padding: 24px 32px` by default. Use `24px` horizontal padding for narrower dashboards.

### Widget Grid

Use CSS Grid for dashboard widgets.

Default widget grid:

```tsx
<div
  style={{
    display: "grid",
    gap: 20,
    gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))",
  }}
>
  <WidgetCard />
  <WidgetCard />
</div>
```

Wide widget grid:

```tsx
<div style={{
  display: "grid",
  gap: 20,
  gridTemplateColumns: "repeat(auto-fill, minmax(480px, 1fr))",
}}>
```

Rules:

- Default grid gap is `20px`.
- Default card minimum width is `340px`.
- Wide chart/table cards can use `minmax(480px, 1fr)`.
- A wide widget may span two columns with `gridColumn: "span 2"` when there is room.
- On narrow screens, widgets must collapse naturally to one column.

### Widget Card

Every data widget must use the same card structure.

```tsx
function WidgetCard({ title, subtitle, children }) {
  return (
    <div
      style={{
        background: "rgba(255, 255, 255, 0.9)",
        border: "1px solid rgba(229, 231, 235, 0.8)",
        borderRadius: 16,
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
        backdropFilter: "blur(8px)",
        boxShadow: "0 1px 4px rgba(0,0,0,0.04)",
        transition: "all 0.35s cubic-bezier(0.4, 0, 0.2, 1)",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "10px 16px",
          borderBottom: "1px solid rgba(229, 231, 235, 0.8)",
          background: "rgba(255,255,255,0.95)",
          backdropFilter: "blur(8px)",
          flexShrink: 0,
        }}
      >
        <div>
          <h3
            style={{
              margin: 0,
              fontSize: 14,
              fontWeight: 600,
              color: "#111827",
            }}
          >
            {title}
          </h3>
          {subtitle && (
            <p
              style={{
                margin: "2px 0 0",
                fontSize: 11,
                color: "#9ca3af",
                lineHeight: 1.3,
              }}
            >
              {subtitle}
            </p>
          )}
        </div>
      </div>
      <div
        style={{
          flex: 1,
          position: "relative",
          overflow: "hidden",
          background: "rgba(249,250,251,0.5)",
        }}
      >
        {children}
      </div>
    </div>
  );
}
```

Hover state:

```css
.widget-card:hover {
  transform: translateY(-4px);
  border-color: rgba(79, 70, 229, 0.2);
  box-shadow:
    0 20px 40px rgba(0, 0, 0, 0.08),
    0 8px 16px rgba(79, 70, 229, 0.06);
}
```

Widget card rules:

- Card radius is `16px`.
- Card header padding is `10px 16px`.
- Card title is `14px`, `600`, `#111827`.
- Card subtitle is `11px`, `#9ca3af`.
- Card body background is `rgba(249,250,251,0.5)`.
- Do not put cards inside other cards.
- Use the card body for charts, tables, KPIs, source trails, and states.

### Category Badges

Use category badges in the top-right of widget headers when useful.

```tsx
<span
  style={{
    fontSize: 10,
    fontWeight: 600,
    textTransform: "uppercase",
    letterSpacing: "0.05em",
    padding: "2px 8px",
    borderRadius: 6,
    border: "1px solid #dbeafe",
    background: "#eff6ff",
    color: "#2563eb",
  }}
>
  markets
</span>
```

Category colors:

| Category    | Background | Text      | Border    |
| ----------- | ---------- | --------- | --------- |
| `markets`   | `#eff6ff`  | `#2563eb` | `#dbeafe` |
| `crypto`    | `#fff7ed`  | `#ea580c` | `#fed7aa` |
| `analytics` | `#f5f3ff`  | `#7c3aed` | `#ede9fe` |
| `tools`     | `#f0fdf4`  | `#16a34a` | `#bbf7d0` |
| `india`     | `#fffbeb`  | `#d97706` | `#fde68a` |
| `heatmaps`  | `#fff1f2`  | `#e11d48` | `#fecdd3` |
| `sector`    | `#f0fdfa`  | `#0d9488` | `#99f6e4` |

### Loading, Empty, And Error UI

Every widget must implement all three states.

Loading state must use a shimmer skeleton, not a blank card or raw spinner.

```css
@keyframes shimmer {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}
.shimmer {
  background-image: linear-gradient(
    90deg,
    #e5e7eb 0%,
    #f3f4f6 50%,
    #e5e7eb 100%
  );
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
  border-radius: 6px;
}
```

Empty state should be centered inside the widget body with:

- An icon or simple visual marker
- A clear message
- A short hint for what to do next
- Minimum height of about `160px`

Error state should be centered inside the widget body with:

- A red icon container using `#fef2f2`
- Error icon/text using `#ef4444`
- Friendly message, not raw stack trace
- Small "Please try again later" or equivalent hint

### Design Tokens

Use only these UI chrome tokens unless data visualization semantics require additional chart colors.

| Token           | Value                                                        | Use                                 |
| --------------- | ------------------------------------------------------------ | ----------------------------------- |
| Primary         | `#4f46e5`                                                    | Active states, icons, hover borders |
| Primary light   | `#eef2ff`                                                    | Ticker badge and icon backgrounds   |
| Primary border  | `#e0e7ff`                                                    | Ticker badge border                 |
| Primary text    | `#4338ca`                                                    | Ticker badge text                   |
| Page background | `linear-gradient(to bottom, rgba(249,250,251,0.8), #ffffff)` | Outer shell only                    |
| Card background | `rgba(255,255,255,0.9)`                                      | Widget cards                        |
| Card header     | `rgba(255,255,255,0.95)`                                     | Card header row                     |
| Card body bg    | `rgba(249,250,251,0.5)`                                      | Card content area                   |
| Header bar      | `rgba(255,255,255,0.95)`                                     | Sticky header                       |
| Border default  | `rgba(229,231,235,0.8)`                                      | Card border and header border       |
| Border hover    | `rgba(79,70,229,0.2)`                                        | Card hover border                   |
| Text primary    | `#111827`                                                    | Titles and primary text             |
| Text secondary  | `#374151`                                                    | Body text and subheadings           |
| Text muted      | `#6b7280`                                                    | Secondary labels                    |
| Text hint       | `#9ca3af`                                                    | Subtitles, timestamps, captions     |
| Error red       | `#ef4444`                                                    | Error icons                         |
| Error bg        | `#fef2f2`                                                    | Error icon container                |

Typography:

| Use             | Size    | Weight | Color     |
| --------------- | ------- | ------ | --------- |
| Dashboard title | 15px    | 700    | `#111827` |
| Widget title    | 14px    | 600    | `#111827` |
| Widget subtitle | 11px    | 400    | `#9ca3af` |
| Body text       | 14px    | 400    | `#374151` |
| Hint / caption  | 12-13px | 400    | `#9ca3af` |
| Badge / label   | 10-12px | 600    | varies    |

Spacing:

| Use                   | Value       |
| --------------------- | ----------- |
| Header height         | `48px`      |
| Main padding          | `24px 32px` |
| Mobile/narrow padding | `24px`      |
| Grid gap              | `20px`      |
| Card radius           | `16px`      |
| Card header padding   | `10px 16px` |

Interactions:

```css
transition: all 0.35s cubic-bezier(0.4, 0, 0.2, 1);
```

### Pre-Submission UI Checklist

- [ ] Layout uses exactly 3 zones: sticky header, scrollable main, optional footer.
- [ ] Header is 48px, blurred white, and has bottom border `#e5e7eb`.
- [ ] Active ticker appears as an indigo pill when selected.
- [ ] Main content scrolls; body/root shell does not.
- [ ] Grid uses `repeat(auto-fill, minmax(340px, 1fr))` or wide `480px` variant.
- [ ] All data widgets use `WidgetCard`.
- [ ] Loading state uses shimmer skeleton.
- [ ] Empty state is present for no ticker or no data.
- [ ] Error state is user-friendly and centered.
- [ ] No custom fonts are loaded; use `system-ui`.
- [ ] UI chrome uses indigo primary plus grayscale, not arbitrary bright colors.
- [ ] Dashboard works at `width: 100%` and `height: 100vh` inside an iframe.

## Auth Standards

### Munshot Dashboard SDK (Required)

All dashboards generated using this skill are embedded inside the Munshot platform as iframes.

Dashboard-to-host communication must use the Munshot Dashboard SDK.

SDK Script:

```html
<script src="https://munshot.s3.ap-south-1.amazonaws.com/SDK+script/munshot-dashboard-sdk.v1.0.0.min.js"></script>
```

Claude must integrate the SDK into every generated dashboard.

Do not implement custom iframe messaging when the SDK can be used.

---

### Authentication Model

Authentication is owned by the Munshot host application.

Generated dashboards must:

- Consume authentication and user context from the SDK.
- Assume the host application manages login, sessions, and token lifecycle.
- Use SDK-provided session information when available.

Generated dashboards must not:

- Create standalone login pages.
- Implement username/password authentication.
- Store credentials in localStorage.
- Embed API keys, secrets, or hardcoded tokens.
- Require users to authenticate separately from Munshot.

---

### Required SDK Lifecycle

Every generated dashboard must:

1. Load the Munshot Dashboard SDK.
2. Initialize the dashboard SDK client during application startup.
3. Register dashboard metadata.
4. Signal dashboard readiness.
5. Request initial host context.
6. Subscribe to host context updates.
7. Handle SDK disconnect and error scenarios.

---

### Context Consumption

Dashboards should expect context from the host application, including:

- User information
- Organization information
- Session information
- Selected ticker or symbol
- Active filters
- Application navigation state

Dashboards must react to context updates without requiring a page refresh.

---

### Communication Standards

Use SDK request/response patterns for:

- Context retrieval
- User selections
- Host-controlled actions
- Operations requiring acknowledgment

Use SDK publish/subscribe patterns for:

- Filter changes
- Dashboard interactions
- Widget events
- Analytics events
- Dashboard telemetry

Topic names must be namespaced.

Examples:

```text
portfolio.ticker.select
analytics.filter.change
dashboard.metric
dashboard.error
```

---

### Security Requirements

Generated dashboards must:

- Trust only SDK-authorized host communication.
- Validate all incoming payloads.
- Handle missing or malformed context safely.
- Respect SDK origin validation.
- Use HTTPS for all external communication.
- Avoid exposing sensitive session data.
- Avoid transmitting secrets through dashboard state.

---

### Error Handling

Generated dashboards must:

- Handle SDK initialization failures.
- Handle missing host context.
- Handle request timeouts.
- Display user-friendly error states.
- Publish dashboard errors through SDK mechanisms when appropriate.

---

### Dashboard Generation Rules

When generating dashboards, Claude must:

- Include SDK integration by default.
- Use SDK communication instead of custom postMessage implementations.
- Use host-provided context whenever possible.
- Keep dashboard logic independent of authentication implementation details.
- Assume dashboards run inside a Munshot iframe environment.

## Datasource Registry

The following datasources are available for dashboard development.

Dashboard implementations should:

- Use registered datasources whenever possible.
- Use `datasource.service` with `base_urls` to build the full API URL.
  - `fastapi` means call `https://fastapi.muns.io` + endpoint path.
  - `nestjs` means call `https://devde.muns.io` + endpoint path.
- Follow documented request and response contracts.
- Respect rate limits and cache recommendations.
- Use host-provided authentication.
- Handle API failures gracefully.
- Avoid introducing undocumented API dependencies.

<!-- GENERATED CONTENT - DO NOT EDIT MANUALLY -->

```yaml
base_urls:
  fastapi: https://fastapi.muns.io
  nestjs: https://devde.muns.io
datasources:
- id: web_search
  name: Web Search
  description: Search the public internet using Brave Search.
  service: fastapi
  endpoint: POST /tools/web-search
  auth:
    type: bearer_jwt
  rate_limit:
    requests_per_minute: 60
  request_fields:
  - field: query
    type: string
    required: true
    description: Search query
  - field: country
    type: string
    required: false
    description: Country code for localized results
  response_fields:
  - field: results
    type: array
    required: true
    description: Structured search results
  cache_ttl_seconds: 300
- id: web_reader
  name: Web Reader
  description: Read and extract content from one or more URLs.
  service: fastapi
  endpoint: POST /tools/web-reader
  auth:
    type: bearer_jwt
  rate_limit:
    requests_per_minute: 60
  request_fields:
  - field: urls
    type: string[]
    required: true
    description: URLs to extract content from
  - field: task
    type: string
    required: false
    description: Optional extraction objective
  response_fields:
  - field: results
    type: object
    required: true
    description: Extracted page content
  cache_ttl_seconds: 300
- id: news_search
  name: News Search
  description: Search recent news articles.
  service: fastapi
  endpoint: POST /tools/news-search
  auth:
    type: bearer_jwt
  rate_limit:
    requests_per_minute: 60
  request_fields:
  - field: query
    type: string
    required: true
  - field: country
    type: string
    required: false
  - field: from_date
    type: date
    required: false
  - field: to_date
    type: date
    required: false
  response_fields:
  - field: results
    type: array
    required: true
    description: News articles
  cache_ttl_seconds: 180
- id: document_search
  name: Document Search
  description: Search proprietary documents indexed in Pinecone.
  service: fastapi
  endpoint: POST /tools/document-search
  auth:
    type: bearer_jwt
  rate_limit:
    requests_per_minute: 60
  request_fields:
  - field: query
    type: string
    required: true
  - field: user_index
    type: integer
    required: true
  - field: ticker_symbol
    type: string|string[]
    required: false
  - field: from_date
    type: date
    required: false
  - field: to_date
    type: date
    required: false
  - field: categories
    type: string[]
    required: false
  - field: doc_indexes
    type: string[]
    required: false
  response_fields:
  - field: structured_data
    type: array
    required: true
  - field: citations
    type: array
    required: false
  cache_ttl_seconds: 120
- id: muns_chat
  name: Muns Chat
  description: Stream an AI answer for a dashboard question using Muns chat context, documents, tickers, and dashboard inputs.
  service: nestjs
  endpoint: POST /chat/chat-muns
  auth:
    type: bearer_jwt
  rate_limit:
    requests_per_minute: 30
  request_fields:
  - field: tasks
    type: string[]
    required: true
    description: User question or task list. Usually provide one dashboard-specific question.
  - field: query_context.chatHistory
    type: object[]
    required: true
    description: Prior chat messages. Use [] for a new dashboard query.
  - field: query_context.TICKER_SYMBOL
    type: string[]
    required: false
    description: Tickers relevant to the dashboard.
  - field: query_context.FROM_DATE
    type: date
    required: false
    description: Start date for time-bounded analysis.
  - field: query_context.TO_DATE
    type: date
    required: false
    description: End date for time-bounded analysis.
  - field: query_context.DOCUMENT_IDS
    type: string[]
    required: false
    description: Uploaded document UUIDs to ground the answer.
  - field: query_context.DOC_INDEX
    type: integer[]
    required: false
    description: Internal document indexes when already known.
  - field: query_context.DASHBOARD_INPUTS
    type: object[]
    required: false
    description: Dashboard extraction inputs to forward into the model context.
  - field: query_context.mode
    type: enum
    required: false
    description: fast or expert. Defaults to expert.
  - field: chat_id
    type: string
    required: false
    description: Existing chat ID when continuing a prior chat.
  response_fields:
  - field: stream
    type: text/event-stream
    required: true
    description: Raw streamed answer chunks from Muns AI.
  - field: X-Chat-Id
    type: header
    required: true
    description: Chat ID created or reused for the request.
  - field: X-Message-Id
    type: header
    required: true
    description: Message ID for the streamed response.
  cache_ttl_seconds: 0
- id: agent_run
  name: Agent Run
  description: Run a registered analyst agent and stream its output for dashboard generation or refresh workflows.
  service: nestjs
  endpoint: POST /agents/run
  auth:
    type: bearer_jwt
  rate_limit:
    requests_per_minute: 20
  request_fields:
  - field: agent_id
    type: string
    required: false
    description: Active analyst UUID. Provide either agent_id or agent_library_id, not both.
  - field: agent_library_id
    type: string
    required: false
    description: Library agent UUID. Provide either agent_library_id or agent_id, not both.
  - field: user_query
    type: string
    required: false
    description: Specific dashboard question or run objective.
  - field: metadata
    type: object
    required: false
    description: Run context such as stock_ticker, from_date, to_date, urls, or autoAddUpcoming.
  - field: DASHBOARD_INPUTS
    type: object[]
    required: false
    description: Dashboard extraction inputs to include in agent context.
  - field: CATEGORIES
    type: string[]
    required: false
    description: Categories to include in the agent query context.
  - field: WRITING_STYLES
    type: string[]
    required: false
    description: Optional registered writing style names for output formatting.
  response_fields:
  - field: stream
    type: text/event-stream
    required: true
    description: Raw streamed agent output.
  - field: X-Active-Analyst-Id
    type: header
    required: true
    description: Active analyst ID used for the run.
  - field: X-Analyst-Output-Id
    type: header
    required: true
    description: Analyst output ID where the run is persisted.
  cache_ttl_seconds: 0
auth_defaults:
  timeout_seconds: 30
  retry_attempts: 3
  retry_backoff_factor: 2.0
  ssl_verify: true
naming_conventions:
  dashboard_file_prefix: dashboard_
  component_file_prefix: component_
  hook_prefix: use
  constant_prefix: DASHBOARD_
```

<!-- END GENERATED CONTENT -->

## Dashboard Patterns

### Core Dashboard Grammar

Dashboards may cover screeners, sector monitors, heatmaps, brand discount trackers, document intelligence views, portfolio/watchlists, or company comparison tools. They must still feel like the same product.

The fixed UI shell is always the 3-zone layout from UI Standards. The flexible dashboard pattern lives inside Zone 2, the scrollable content area.

```text
Zone 2 Content Order
+-- Context/filter widgets
+-- KPI summary widgets
+-- Primary analysis widget(s)
+-- Supporting insight widgets
+-- Detail/drilldown widgets
+-- Source/provenance widgets
```

Standardize the hierarchy, not the exact chart type.

### Content Hierarchy

Every dashboard should include these roles when the data supports them:

- **Context / Filters**: The controls that define the universe, period, entity, source type, or segment.
- **KPI Summary**: Three to five compact metrics that summarize the current state.
- **Primary Analysis**: The dominant chart, table, heatmap, matrix, or extraction result.
- **Supporting Insights**: Risk, opportunity, watch, change, or explanation widgets.
- **Detail / Drilldown**: Table, ranked list, source-level breakdown, product list, or company comparison.
- **Source / Trust**: Source trail, extraction time, data freshness, API name, citation count, or confidence note.

These roles should be implemented as `WidgetCard` components. Do not invent a different visual shell for each role.

### Widget Placement

Use widget width to create hierarchy inside the grid:

- KPI widgets: normal `WidgetCard`, usually one grid cell each.
- Filter/context widget: normal or wide card depending on complexity.
- Primary analysis widget: wide card, often `gridColumn: "span 2"` on desktop.
- Insight widgets: normal cards grouped near the primary analysis.
- Detail tables: wide cards.
- Source trail: normal card unless source data is the main subject.

Recommended arrangement:

```text
Row 1: filter/context card, optional status/source freshness card
Row 2: KPI cards
Row 3: wide primary analysis card + insight cards
Row 4: wide detail table/card + source trail card
```

On small screens, the grid naturally collapses to one column. Preserve the same order.

### Dashboard Type Variants

Choose the primary widget based on the dashboard type:

- **Screener**: Primary widget is a dense filterable table. KPI widgets summarize count, median valuation, strongest signal, and latest update.
- **Heatmap**: Primary widget is a color-coded matrix. KPI widgets summarize strongest cluster, weakest cluster, dispersion, and freshness.
- **Sector Dashboard**: Primary widget is a momentum, trend, or sector comparison chart. Detail widget compares companies.
- **Company Dashboard**: Primary widget is a company-specific operating or market trend. Supporting widgets cover risks, catalysts, filings, and sources.
- **Brand Discounts Dashboard**: Primary widget is a discount or product matrix. Detail widget lists brand, product, retailer, discount depth, price, and source date.
- **Document Intelligence Dashboard**: Primary widget is an answer, extraction summary, or claim map. Detail widget lists extracted claims and citations.
- **Portfolio / Watchlist Dashboard**: Primary widget is holdings or watchlist ranking. Supporting widgets highlight alerts, exposures, and recent changes.

Do not force every dashboard to use the same chart. The consistent part is the shell, widget card structure, hierarchy, and state handling.

### KPI Standards

KPI widgets must be meaningful, not decorative.

Each KPI should include:

- Short label
- Main value
- Trend or comparison when available
- Time period or scope
- Status color only when it adds meaning

Good KPI examples:

- Sector Score: `72`, `+5 pts vs prior month`
- Avg MLR Pressure: `84.6%`, `+120 bps QoQ`
- Products on Discount: `248`, `+18% WoW`
- Screened Companies: `412`, `32 passed filters`
- Source Freshness: `18h`, `All core feeds updated`

Avoid vague KPI labels like `Total Data`, `Overall Info`, or duplicate metrics.

### Insight Standards

Insight widgets should explain the data, not repeat it.

Use concise blocks with one of these roles:

- **Risk**: What could hurt performance or confidence.
- **Opportunity**: What looks attractive or improving.
- **Watch**: What needs monitoring but is not decisive yet.
- **Change**: What moved since the last refresh.
- **Source Note**: What the data is based on or where confidence is limited.

Each insight should have:

- A short category label or badge
- One direct sentence
- One supporting sentence

### Table Standards

Tables are for drilldown and comparison.

Financial dashboard tables should:

- Use compact rows and clear column labels.
- Keep the first column visually prominent.
- Use status chips for risk, confidence, direction, or category.
- Include mini trends only when they improve scan speed.
- Support sorting, filtering, pagination, or virtual scrolling when data is large.
- Avoid loading more than 10,000 rows into the DOM at once.

Common columns by dashboard type:

- Screener: entity, ticker, score, valuation, growth, quality, signal, source date.
- Sector: company, score, operating metric, risk, valuation, signal.
- Heatmap: row group, column group, value, change, confidence.
- Discounts: brand, product, retailer, list price, discount, final price, source date.
- Document intelligence: claim, source, confidence, extracted value, citation.

### Source And Trust Standards

Every dashboard that uses external, AI-extracted, web, news, or document-derived data must show source context.

Include at least one of:

- Source trail widget
- Data source attribution
- Last updated timestamp
- Extraction timestamp
- Citation count
- Confidence or freshness indicator

Source trail entries should be short:

```text
Source title
What was extracted, and when
```

### State Standards

Follow the UI Standards state components inside every widget:

- **Loading**: shimmer skeleton matching the final widget shape.
- **Refreshing**: keep previous data visible and show a subtle refresh state.
- **Empty**: centered empty state with a message and next-step hint.
- **Partial data**: render available widgets and mark unavailable ones clearly.
- **API error**: friendly centered error state; never show raw stack traces.
- **Auth/context error**: explain that host session or selected context is unavailable.

### Performance Standards

- Debounce filter changes by at least 300ms.
- Cache static metadata, filter options, and slow-changing source lists.
- Use pagination or virtual scrolling for large tables.
- Lazy-load expensive secondary widgets when possible.
- Avoid repeated calls to the same datasource with identical parameters.
- Respect datasource `cache_ttl_seconds` and `rate_limit` from the registry.

### Implementation Rules For Claude

When generating a dashboard, Claude must:

- Build the actual dashboard as the first screen, not a landing page.
- Use the 3-zone shell from UI Standards.
- Use `WidgetCard` for all data widgets.
- Use only datasources registered in the Datasource Registry.
- Put dashboard roles in this order: filters/context, KPIs, primary analysis, insights, detail, sources.
- Select the primary widget based on the dashboard type.
- Keep the interface dense, calm, and suitable for repeated financial analysis.
- Include loading, empty, error, and partial-data states.
- Include source freshness or provenance when using extracted, web, news, document, or AI-generated data.
- Keep layout responsive without changing the meaning or order of sections.
- Avoid decorative UI that does not support analysis.

## Examples

Use examples as compact blueprints, not long case studies. Every example still uses the 3-zone shell, `WidgetCard`, registered datasources, and the standard order: filters/context, KPIs, primary analysis, insights, detail, sources.

### Screener Dashboard

- **Purpose**: Filter and rank companies by financial, market, or custom signals.
- **Primary widget**: Wide screener table.
- **KPI widgets**: screened companies, companies passing filters, median valuation, strongest signal.
- **Detail widget**: selected company or row breakdown.
- **Source widget**: data freshness and datasource list.

### Sector Intelligence Dashboard

- **Purpose**: Compare companies and signals within a sector.
- **Primary widget**: Wide sector momentum, comparison chart, or company matrix.
- **KPI widgets**: sector score, average pressure metric, policy/risk level, source freshness.
- **Insight widgets**: risk, opportunity, watch, and change notes.
- **Detail widget**: company comparison table.
- **Source widget**: filings, news, web, or document source trail.

### Heatmap Dashboard

- **Purpose**: Show relative strength, weakness, concentration, or dispersion across many entities.
- **Primary widget**: Wide heatmap matrix.
- **KPI widgets**: strongest cluster, weakest cluster, dispersion, latest update.
- **Insight widgets**: notable outliers and changes since prior period.
- **Detail widget**: selected cell breakdown table.
- **Source widget**: source freshness and confidence notes.

### Brand Discounts Dashboard

- **Purpose**: Track discounts, pricing changes, and retailer behavior for brands/products.
- **Primary widget**: Wide discount matrix or product table.
- **KPI widgets**: products tracked, average discount, deepest discount, retailers active.
- **Insight widgets**: pricing pressure, unusual discounting, restock or promotion notes.
- **Detail widget**: product rows with brand, retailer, list price, final price, discount, source date.
- **Source widget**: web reader or source trail entries.

### Document Intelligence Dashboard

- **Purpose**: Convert documents, filings, transcripts, or web pages into structured findings.
- **Primary widget**: Wide extraction summary or answer widget.
- **KPI widgets**: documents read, claims extracted, citation count, confidence/freshness.
- **Insight widgets**: key risks, opportunities, contradictions, and watch items.
- **Detail widget**: claim table with extracted value, source, citation, confidence.
- **Source widget**: required source trail with extraction timestamps.
