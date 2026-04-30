// ScopeLedger Mock Data
window.SCOPEDATA = {

  project: {
    name: "GSA Building 452",
    subtitle: "Mechanical / Electrical Upgrade — Phase 2",
    currentPackage: "Rev 04",
    packageDate: "Apr 15, 2026",
    totalSheets: 47,
    stats: { pending: 14, accepted: 31, rejected: 6, needsCheck: 3 },
    exportReady: false,
    driveFolder: "https://drive.google.com/drive/folders/example"
  },

  revisionPackages: [
    { id: "rev04", label: "Rev 04", date: "2026-04-15", sheets: 12, changes: 51, status: "active",   discipline: "Mech / Elec / Arch" },
    { id: "rev03", label: "Rev 03", date: "2026-02-28", sheets: 8,  changes: 34, status: "complete", discipline: "Mechanical" },
    { id: "rev02", label: "Rev 02", date: "2025-11-12", sheets: 15, changes: 67, status: "complete", discipline: "All disciplines" },
    { id: "rev01", label: "Rev 01", date: "2025-07-20", sheets: 22, changes: 89, status: "complete", discipline: "All disciplines" },
  ],

  changes: [
    { id: "c001", sheet: "M-201", title: "2nd Floor Mechanical Room Plan",   rev: "Rev 04", cloud: "A", discipline: "Mechanical",    status: "pending",  needsCheck: false, scope: "Ductwork rerouted around new beam at gridline D-7. Supply trunk reduced from 18×14 to 16×12 for 6'-0\" run." },
    { id: "c002", sheet: "M-201", title: "2nd Floor Mechanical Room Plan",   rev: "Rev 04", cloud: "B", discipline: "Mechanical",    status: "pending",  needsCheck: true,  scope: "VAV box VB-2-04 relocated 3'-6\" north per RFI-0047. New flex duct connection required to existing grille G-22." },
    { id: "c003", sheet: "M-301", title: "3rd Floor HVAC Plan",              rev: "Rev 04", cloud: "A", discipline: "Mechanical",    status: "accepted", needsCheck: false, scope: "Return air plenum wall relocated 2'-0\" east at gridlines C-D/4-5. Ceiling tile grid to match." },
    { id: "c004", sheet: "M-301", title: "3rd Floor HVAC Plan",              rev: "Rev 04", cloud: "B", discipline: "Mechanical",    status: "accepted", needsCheck: false, scope: "New exhaust fan EF-3-01 added, 650 CFM. Power per E-301." },
    { id: "c005", sheet: "M-401", title: "4th Floor HVAC Plan",              rev: "Rev 04", cloud: "A", discipline: "Mechanical",    status: "rejected", needsCheck: false, scope: "Diffuser relocation at gridline E-8 — duplicate of Rev 03 cloud C. Already priced." },
    { id: "c006", sheet: "M-501", title: "Mechanical Schedules",             rev: "Rev 04", cloud: "A", discipline: "Mechanical",    status: "pending",  needsCheck: false, scope: "AHU-4 supply static pressure revised from 2.5\" WC to 3.0\" WC. Fan selection to be resubmitted." },
    { id: "c007", sheet: "M-502", title: "Mechanical Details — Duct",        rev: "Rev 04", cloud: "A", discipline: "Mechanical",    status: "pending",  needsCheck: true,  scope: "Flexible duct connection detail revised: max 18\" per SMACNA. Verify field condition matches." },
    { id: "c008", sheet: "E-201", title: "2nd Floor Power Plan",             rev: "Rev 04", cloud: "A", discipline: "Electrical",    status: "accepted", needsCheck: false, scope: "New 20A circuit added for VAV controllers in MER-205. Panel LP-2 breaker 37 reserved." },
    { id: "c009", sheet: "E-201", title: "2nd Floor Power Plan",             rev: "Rev 04", cloud: "B", discipline: "Electrical",    status: "pending",  needsCheck: false, scope: "Conduit routing revised above ceiling at G-5 to avoid conflict with relocated ductwork (ref M-201)." },
    { id: "c010", sheet: "E-301", title: "3rd Floor Power Plan",             rev: "Rev 04", cloud: "A", discipline: "Electrical",    status: "accepted", needsCheck: false, scope: "Emergency disconnect added for EF-3-01 per NEC 430.102. Location: column C-4, 5'-0\" AFF." },
    { id: "c011", sheet: "E-302", title: "3rd Floor Lighting Plan",          rev: "Rev 04", cloud: "A", discipline: "Electrical",    status: "pending",  needsCheck: false, scope: "Occupancy sensor coverage revised at corridor 340. Add sensor OS-3-14, tie to existing circuit L3-22." },
    { id: "c012", sheet: "E-303", title: "Electrical Panel Schedules",       rev: "Rev 04", cloud: "A", discipline: "Electrical",    status: "pending",  needsCheck: false, scope: "Panel MCC-4 breaker assignments updated. Spare breaker 41 reassigned to new HVAC controls circuit." },
    { id: "c013", sheet: "A-102", title: "2nd Floor Architectural Plan",     rev: "Rev 04", cloud: "A", discipline: "Architectural", status: "accepted", needsCheck: false, scope: "Mechanical room MER-205 partition wall relocated 1'-6\" per structural coordination. Door swing revised." },
    { id: "c014", sheet: "A-203", title: "Wall Types & Details",             rev: "Rev 04", cloud: "A", discipline: "Architectural", status: "rejected", needsCheck: false, scope: "Wall type W-7 fire rating note corrected to 2-hr. Administrative revision — already in record set." },
    { id: "c015", sheet: "M-101", title: "1st Floor Mechanical Plan",        rev: "Rev 04", cloud: "A", discipline: "Mechanical",    status: "pending",  needsCheck: false, scope: "Chilled water supply/return risers relocated 8\" south to clear new beam B-12. Insulation to continue per spec." },
    { id: "c016", sheet: "M-101", title: "1st Floor Mechanical Plan",        rev: "Rev 04", cloud: "B", discipline: "Mechanical",    status: "pending",  needsCheck: false, scope: "Condensate drain revised at AHU-1. Trap added per manufacturer requirement, min 3\" seal depth." },
    { id: "c017", sheet: "E-304", title: "Electrical One-Line Diagram",      rev: "Rev 04", cloud: "A", discipline: "Electrical",    status: "pending",  needsCheck: true,  scope: "Feeder to MCC-4 upsized from #3 AWG to #1 AWG per voltage drop recalc. Conduit size to be confirmed." },
  ],

  sheets: [
    { id: "sh001", sheet: "M-101",  title: "1st Floor Mechanical Plan",        rev: "Rev 04", prevRev: "Rev 03", discipline: "Mechanical",    status: "active",     changes: 2, warnings: 0 },
    { id: "sh002", sheet: "M-102",  title: "1st Floor Mech Plan — North",      rev: "Rev 03", prevRev: "Rev 02", discipline: "Mechanical",    status: "active",     changes: 0, warnings: 0 },
    { id: "sh003", sheet: "M-201",  title: "2nd Floor Mechanical Room Plan",   rev: "Rev 04", prevRev: "Rev 02", discipline: "Mechanical",    status: "active",     changes: 2, warnings: 0 },
    { id: "sh004", sheet: "M-301",  title: "3rd Floor HVAC Plan",              rev: "Rev 04", prevRev: "Rev 03", discipline: "Mechanical",    status: "active",     changes: 2, warnings: 0 },
    { id: "sh005", sheet: "M-401",  title: "4th Floor HVAC Plan",              rev: "Rev 04", prevRev: "Rev 03", discipline: "Mechanical",    status: "active",     changes: 1, warnings: 0 },
    { id: "sh006", sheet: "M-501",  title: "Mechanical Schedules",             rev: "Rev 04", prevRev: "Rev 03", discipline: "Mechanical",    status: "active",     changes: 1, warnings: 1 },
    { id: "sh007", sheet: "M-502",  title: "Mechanical Details — Duct",        rev: "Rev 04", prevRev: "Rev 02", discipline: "Mechanical",    status: "active",     changes: 1, warnings: 0 },
    { id: "sh008", sheet: "E-201",  title: "2nd Floor Power Plan",             rev: "Rev 04", prevRev: "Rev 03", discipline: "Electrical",    status: "active",     changes: 2, warnings: 0 },
    { id: "sh009", sheet: "E-301",  title: "3rd Floor Power Plan",             rev: "Rev 04", prevRev: "Rev 04", discipline: "Electrical",    status: "active",     changes: 1, warnings: 0 },
    { id: "sh010", sheet: "E-302",  title: "3rd Floor Lighting Plan",          rev: "Rev 04", prevRev: "Rev 03", discipline: "Electrical",    status: "active",     changes: 1, warnings: 0 },
    { id: "sh011", sheet: "E-303",  title: "Electrical Panel Schedules",       rev: "Rev 04", prevRev: "Rev 03", discipline: "Electrical",    status: "active",     changes: 1, warnings: 2 },
    { id: "sh012", sheet: "E-304",  title: "Electrical One-Line Diagram",      rev: "Rev 04", prevRev: "Rev 03", discipline: "Electrical",    status: "active",     changes: 1, warnings: 0 },
    { id: "sh013", sheet: "A-102",  title: "2nd Floor Architectural Plan",     rev: "Rev 04", prevRev: "Rev 03", discipline: "Architectural", status: "active",     changes: 1, warnings: 0 },
    { id: "sh014", sheet: "A-203",  title: "Wall Types & Details",             rev: "Rev 04", prevRev: "Rev 03", discipline: "Architectural", status: "active",     changes: 1, warnings: 0 },
    { id: "sh015", sheet: "M-201",  title: "2nd Floor Mechanical Room Plan",   rev: "Rev 03", prevRev: "Rev 02", discipline: "Mechanical",    status: "superseded", changes: 3, warnings: 0 },
    { id: "sh016", sheet: "M-301",  title: "3rd Floor HVAC Plan",              rev: "Rev 03", prevRev: "Rev 02", discipline: "Mechanical",    status: "superseded", changes: 2, warnings: 0 },
    { id: "sh017", sheet: "E-201",  title: "2nd Floor Power Plan",             rev: "Rev 03", prevRev: "Rev 02", discipline: "Electrical",    status: "superseded", changes: 2, warnings: 0 },
  ],

  conformedSheets: [
    { sheet: "M-101", title: "1st Floor Mechanical Plan",        currentRev: "Rev 04", prevRev: "Rev 03", revised: true  },
    { sheet: "M-102", title: "1st Floor Mech Plan — North",      currentRev: "Rev 03", prevRev: "Rev 02", revised: false },
    { sheet: "M-103", title: "1st Floor Mech Plan — South",      currentRev: "Rev 02", prevRev: "Rev 01", revised: false },
    { sheet: "M-201", title: "2nd Floor Mechanical Room Plan",   currentRev: "Rev 04", prevRev: "Rev 02", revised: true  },
    { sheet: "M-301", title: "3rd Floor HVAC Plan",              currentRev: "Rev 04", prevRev: "Rev 03", revised: true  },
    { sheet: "M-401", title: "4th Floor HVAC Plan",              currentRev: "Rev 04", prevRev: "Rev 03", revised: true  },
    { sheet: "M-501", title: "Mechanical Schedules",             currentRev: "Rev 04", prevRev: "Rev 03", revised: true  },
    { sheet: "M-502", title: "Mechanical Details — Duct",        currentRev: "Rev 04", prevRev: "Rev 02", revised: true  },
    { sheet: "M-503", title: "Mechanical Details — Equipment",   currentRev: "Rev 02", prevRev: "Rev 01", revised: false },
    { sheet: "E-201", title: "2nd Floor Power Plan",             currentRev: "Rev 04", prevRev: "Rev 03", revised: true  },
    { sheet: "E-202", title: "2nd Floor Lighting Plan",          currentRev: "Rev 02", prevRev: "Rev 01", revised: false },
    { sheet: "E-301", title: "3rd Floor Power Plan",             currentRev: "Rev 04", prevRev: "Rev 04", revised: true  },
    { sheet: "E-302", title: "3rd Floor Lighting Plan",          currentRev: "Rev 04", prevRev: "Rev 03", revised: true  },
    { sheet: "E-303", title: "Electrical Panel Schedules",       currentRev: "Rev 04", prevRev: "Rev 03", revised: true  },
    { sheet: "E-304", title: "Electrical One-Line Diagram",      currentRev: "Rev 04", prevRev: "Rev 03", revised: true  },
    { sheet: "A-101", title: "1st Floor Architectural Plan",     currentRev: "Rev 02", prevRev: "Rev 01", revised: false },
    { sheet: "A-102", title: "2nd Floor Architectural Plan",     currentRev: "Rev 04", prevRev: "Rev 03", revised: true  },
    { sheet: "A-203", title: "Wall Types & Details",             currentRev: "Rev 04", prevRev: "Rev 03", revised: true  },
  ],

  exportHistory: [
    { id: "ex01", timestamp: "2026-04-14 15:32", package: "Rev 03", accepted: 34, rejected: 4,
      files: ["ScopeLedger_Rev03_20260414.xlsx", "changes_Rev03.csv", "review_packet_Rev03.pdf"] },
    { id: "ex02", timestamp: "2026-02-22 09:17", package: "Rev 02", accepted: 63, rejected: 4,
      files: ["ScopeLedger_Rev02_20260222.xlsx", "changes_Rev02.csv", "review_packet_Rev02.pdf"] },
  ],

  diagnostics: [
    { file: "Rev04_Mechanical.pdf",  pages: 24, sizeMb: "18.4", clouds: 32, vectorText: true,  issues: [] },
    { file: "Rev04_Electrical.pdf",  pages: 12, sizeMb: "9.2",  clouds: 14, vectorText: true,  issues: [] },
    { file: "Rev04_Architectural.pdf", pages: 8, sizeMb: "6.7", clouds: 5,  vectorText: false, issues: ["Rasterized text on A-102, A-203 — OCR applied, review scope text carefully"] },
    { file: "Rev03_Mechanical.pdf",  pages: 18, sizeMb: "14.1", clouds: 28, vectorText: true,  issues: [] },
    { file: "Rev03_Electrical.pdf",  pages: 10, sizeMb: "7.8",  clouds: 10, vectorText: true,  issues: [] },
  ]
};
