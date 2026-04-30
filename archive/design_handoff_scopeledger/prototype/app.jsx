// Main App — routing + tweaks panel integration
// Depends on: all page components, tweaks-panel

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "theme": "dark",
  "accent": "amber"
}/*EDITMODE-END*/;

const ACCENT_MAP = {
  amber:    { accent: 'oklch(0.71 0.130 68)',  accentHover: 'oklch(0.76 0.130 68)', accentDim: 'oklch(0.71 0.130 68 / 0.32)', accentQuiet: 'oklch(0.71 0.130 68 / 0.12)', lightAccent: 'oklch(0.55 0.135 58)', lightAccentHover: 'oklch(0.49 0.135 58)' },
  chrome:   { accent: 'oklch(0.68 0.120 225)', accentHover: 'oklch(0.73 0.120 225)', accentDim: 'oklch(0.68 0.120 225 / 0.32)', accentQuiet: 'oklch(0.68 0.120 225 / 0.12)', lightAccent: 'oklch(0.48 0.110 225)', lightAccentHover: 'oklch(0.42 0.110 225)' },
  hiviz:    { accent: 'oklch(0.82 0.170 115)', accentHover: 'oklch(0.87 0.170 115)', accentDim: 'oklch(0.82 0.170 115 / 0.28)', accentQuiet: 'oklch(0.82 0.170 115 / 0.10)', lightAccent: 'oklch(0.52 0.160 115)', lightAccentHover: 'oklch(0.46 0.160 115)' },
};

// Demo Switcher — always-visible floating strip for live demos
const ACCENT_DOTS = {
  amber:  { color: 'oklch(0.71 0.130 68)',  label: 'Amber'  },
  chrome: { color: 'oklch(0.68 0.120 225)', label: 'Chrome' },
  hiviz:  { color: 'oklch(0.82 0.170 115)', label: 'Hi-Viz' },
};

function DemoSwitcher({ tweaks, setTweak }) {
  const isDark = tweaks.theme === 'dark';

  const switcherStyle = {
    position: 'fixed',
    bottom: 20,
    right: 20,
    zIndex: 9000,
    display: 'flex',
    alignItems: 'center',
    gap: 2,
    background: isDark ? 'oklch(0.19 0.009 55)' : 'oklch(0.99 0.003 55)',
    border: `1px solid ${isDark ? 'oklch(0.28 0.007 55)' : 'oklch(0.82 0.005 55)'}`,
    borderRadius: 8,
    padding: '6px 10px',
    boxShadow: '0 4px 16px oklch(0 0 0 / 0.5)',
    userSelect: 'none',
  };

  const divider = React.createElement('div', {
    style: { width: 1, height: 16, background: isDark ? 'oklch(0.28 0.007 55)' : 'oklch(0.82 0.005 55)', margin: '0 6px' }
  });

  const labelStyle = {
    fontSize: 10,
    fontFamily: 'var(--font-mono)',
    color: isDark ? 'oklch(0.42 0.005 55)' : 'oklch(0.58 0.005 55)',
    letterSpacing: '0.06em',
    textTransform: 'uppercase',
    marginRight: 6,
    whiteSpace: 'nowrap',
  };

  const modeBtn = (mode, label) => React.createElement('button', {
    key: mode,
    onClick: () => setTweak('theme', mode),
    style: {
      height: 24,
      padding: '0 10px',
      borderRadius: 4,
      border: 'none',
      cursor: 'pointer',
      fontSize: 11,
      fontFamily: 'var(--font-mono)',
      fontWeight: 500,
      transition: 'background 120ms, color 120ms',
      background: tweaks.theme === mode
        ? (isDark ? 'oklch(0.28 0.007 55)' : 'oklch(0.88 0.005 55)')
        : 'transparent',
      color: tweaks.theme === mode
        ? (isDark ? 'oklch(0.92 0.008 55)' : 'oklch(0.15 0.009 55)')
        : (isDark ? 'oklch(0.50 0.005 55)' : 'oklch(0.55 0.005 55)'),
    }
  }, label);

  const accentDot = (id, { color, label }) => React.createElement('button', {
    key: id,
    onClick: () => setTweak('accent', id),
    title: label,
    style: {
      width: 18,
      height: 18,
      borderRadius: '50%',
      border: tweaks.accent === id
        ? `2px solid ${isDark ? 'oklch(0.92 0.008 55)' : 'oklch(0.15 0.009 55)'}`
        : '2px solid transparent',
      background: color,
      cursor: 'pointer',
      padding: 0,
      boxSizing: 'border-box',
      transition: 'border-color 120ms, transform 120ms',
      transform: tweaks.accent === id ? 'scale(1.15)' : 'scale(1)',
      outline: 'none',
    }
  });

  return React.createElement('div', { style: switcherStyle },
    React.createElement('span', { style: labelStyle }, 'Theme'),
    modeBtn('dark',  'Dark'),
    modeBtn('light', 'Light'),
    divider,
    React.createElement('span', { style: labelStyle }, 'Accent'),
    React.createElement('div', { style: { display: 'flex', gap: 5, alignItems: 'center' } },
      Object.entries(ACCENT_DOTS).map(([id, v]) => accentDot(id, v))
    )
  );
}


  const [tweaks, setTweak] = window.useTweaks(TWEAK_DEFAULTS);

  // Route state: { page, id }
  const [route, setRoute] = React.useState({ page: 'overview', id: null });

  const navigate = (page, id = null) => setRoute({ page, id });

  // Apply theme
  React.useEffect(() => {
    document.documentElement.setAttribute('data-theme', tweaks.theme);
  }, [tweaks.theme]);

  // Apply accent
  React.useEffect(() => {
    const map = ACCENT_MAP[tweaks.accent] || ACCENT_MAP.amber;
    const root = document.documentElement;
    const isLight = tweaks.theme === 'light';
    root.style.setProperty('--accent',        isLight ? map.lightAccent      : map.accent);
    root.style.setProperty('--accent-hover',  isLight ? map.lightAccentHover : map.accentHover);
    root.style.setProperty('--accent-dim',    map.accentDim);
    root.style.setProperty('--accent-quiet',  map.accentQuiet);
    root.style.setProperty('--accent-text',   isLight ? map.lightAccent      : map.accent);
  }, [tweaks.accent, tweaks.theme]);

  // Always compact density
  React.useEffect(() => {
    document.documentElement.style.setProperty('--text-base', '12px');
    document.documentElement.style.setProperty('--sp-3', '8px');
    document.documentElement.style.setProperty('--sp-4', '12px');
  }, []);

  const renderPage = () => {
    switch (route.page) {
      case 'overview':     return React.createElement(window.Overview,      { navigate });
      case 'changes':      return React.createElement(window.ReviewChanges, { navigate });
      case 'change-detail':return React.createElement(window.ChangeDetail,  { changeId: route.id || window.SCOPEDATA.changes[0].id, navigate });
      case 'sheets':       return React.createElement(window.Drawings,      { navigate });
      case 'sheet-detail': return React.createElement(window.SheetDetail,   { sheetId: route.id || window.SCOPEDATA.sheets[2].id, navigate });
      case 'conformed':    return React.createElement(window.LatestSet,     { navigate });
      case 'export':       return React.createElement(window.ExportPage,    { navigate });
      case 'diagnostics':  return React.createElement(window.Diagnostics,   { navigate });
      default:             return React.createElement(window.Overview,      { navigate });
    }
  };

  const navPage = ['change-detail', 'sheet-detail'].includes(route.page)
    ? (route.page === 'change-detail' ? 'changes' : 'sheets')
    : route.page;

  return React.createElement('div', { className: 'app-shell' },
    React.createElement(window.Nav, { current: navPage, navigate }),

    React.createElement('main', { style: { flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' } },
      renderPage()
    ),

    // Demo switcher — always-visible bottom-right strip
    React.createElement(DemoSwitcher, { tweaks, setTweak })
  );
}

// Add spin keyframe for generate button
const style = document.createElement('style');
style.textContent = '@keyframes spin { to { transform: rotate(360deg); } }';
document.head.appendChild(style);

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(React.createElement(App));
