Context: InsightOS – Minimalistic Frontend Redesign

1. Project Overview

Product: InsightOS (formerly DerivInsight)
Type: Autonomous Retail Decision Engine
Users: Category Managers, Retail Executives, Inventory Planners

Core capabilities:





Natural Language → SQL + Insights



Custom offline ML models (Demand Forecast, Stockout Risk, Reorder)



Live sync (Tally, Google Sheets, Excel)



Auto Insights (proactive alerts)



Autonomous Purchase Order workflow



Manual data import into live_data folder



2. Redesign Goal

Redesign the entire frontend to be minimalistic, professional, and high-trust.

Style name: Minimal Command

Design Principles





Extremely clean and calm



High information density with generous whitespace



Sharp geometry (almost no border-radius)



Orange used sparingly and purposefully



No glassmorphism, no heavy glows, no decorative orbs



Desktop-first, executive-grade interface



Results tables and visualizations (charts) must always be clearly visible and correctly rendered



3. Color System (Strict)

:root {
  /* Backgrounds */
  --bg-primary:     #050505;
  --bg-secondary:   #0A0A0A;
  --bg-tertiary:    #111111;
  --bg-elevated:    #141414;

  /* Accent - use sparingly */
  --orange:         #FF6B00;
  --orange-hover:   #FF8C00;
  --orange-muted:   rgba(255, 107, 0, 0.12);

  /* Text */
  --text-primary:   #F5F5F5;
  --text-secondary: #A0A0A0;
  --text-muted:     #666666;

  /* Borders */
  --border:         rgba(255, 255, 255, 0.06);
  --border-strong:  rgba(255, 255, 255, 0.12);

  /* Semantic */
  --success:        #00C853;
  --warning:        #FFAB00;
  --critical:       #FF1744;
}



4. Typography & Geometry





Font: Inter (UI) + JetBrains Mono (data / SQL / metrics)



Border-radius: 0px – 2px maximum



Prefer sharp rectangles



Thin 1px borders



Clear visual hierarchy through size, weight, and spacing only



5. Layout Structure

┌────────────────────────────────────────────────────────────┐
│  LOGO   InsightOS       Query   Sentinel   Insights   ● LIVE │
├────────────┬───────────────────────────────────────────────┤
│            │                                               │
│  SIDEBAR   │              MAIN WORKSPACE                   │
│            │                                               │
│  - Domain  │   (Chat / Dashboard / Insights Board)         │
│  - Examples│                                               │
│  - Sync    │                                               │
│  - Risk    │                                               │
│  - More ▾  │                                               │
│            │                                               │
└────────────┴───────────────────────────────────────────────┘

Keep the three existing modes:





Query Assistant



Sentinel Mode



Auto Insights



6. Data Import Feature (Important)

There must be an option for the user to select a file or select a directory to import data into the live_data folder.

Placement Rules





This feature must NOT be visible directly on the main screen or sidebar by default.



It should be placed under a secondary menu, for example:





A “More” or “Settings” or “Data” dropdown in the sidebar



Or under a “⋯” / overflow menu



Or inside a collapsible “Data Sources” section

Required Options





Select File → allows user to pick one or more .xlsx / .xls / .csv files



Select Directory → allows user to choose a folder (for bulk import)

Behavior





After selection, files should be uploaded/copied to the backend live_data folder



Show clear success / error feedback



Optionally trigger a sync after successful import



Keep the UI minimal — only show the import controls when the menu is opened



7. Component Rules (Minimalistic)





Cards: Solid dark background, 1px subtle border, no shadow or glow



Active state: Thin orange left border or underline



Buttons:





Primary → solid orange



Secondary → outline



Ghost → text only



Tables: Clean, sharp, orange header text only. Must display full query results correctly with proper column alignment and scrolling when needed.



Charts / Visualizations: Must render correctly with sufficient height, clear labels, and proper contrast. Use orange as the primary series color. Never hide or collapse charts by default.



Inputs: Dark background, subtle border, orange focus ring (thin)



Status chips: Small, sharp, with left color bar



SQL blocks: Pure black + mono font + thin border



Menu / Dropdown: Clean, sharp, dark elevated background, subtle border



8. Critical Requirements for Results & Visualizations





Query results (tables) must always be fully visible and readable



Charts generated from query results must render properly with correct dimensions



Never hide the results panel or charts behind collapsed sections by default



Provide clear visual separation between chat, SQL, insights, table, and chart



Ensure charts have enough height (minimum 280–320px) and respond to container width



Tables should support horizontal scroll if columns overflow



Maintain good contrast so data remains readable on dark background



9. What to Avoid Completely





Glassmorphism / backdrop-blur



Glowing effects and floating orbs



Soft rounded corners



Multiple accent colors



Decorative illustrations



Heavy animations



Cluttered sidebars



Hidden or collapsed results/visualization areas



Making the file/directory import option visible by default on the main UI



10. Success Criteria

The redesigned website should feel:





Professional and executive-ready



Calm and focused



Highly scannable



Modern high-tech without looking “cyber”



Easy to extend later



Results and visualizations always visible and correctly displayed



Data import available but cleanly tucked under a menu

Tone: Precise • Calm • Authoritative • Clean



11. Implementation Priority





Global design system (colors, typography, spacing)



Header + Sidebar layout



Query Assistant mode (with fully visible results table + charts)



Data Import option (under menu / More section)



Sentinel Dashboard



Auto Insights board



Final polish (empty states, loading, responsiveness)



Use this document as the single source of truth for the minimalistic redesign of InsightOS.

