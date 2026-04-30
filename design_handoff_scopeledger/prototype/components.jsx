// Shared Components — exports to window
// Depends on: window.SCOPEDATA

const ICONS = {
  home: "M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z",
  'check-square': "M9 11l3 3L22 4M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11",
  layers: "M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5",
  grid: "M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z",
  download: "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3",
  wrench: "M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z",
  'chevron-left': "M15 18l-6-6 6-6",
  'chevron-right': "M9 18l6-6-6-6",
  'arrow-left': "M19 12H5M12 19l-7-7 7-7",
  check: "M20 6L9 17l-5-5",
  x: "M18 6L6 18M6 6l12 12",
  'alert-triangle': "M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0zM12 9v4M12 17h.01",
  'external-link': "M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6M15 3h6v6M10 14L21 3",
  'file-down': "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6M12 18v-6M9 15l3 3 3-3",
  clock: "M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10zM12 6v6l4 2",
  filter: "M22 3H2l8 9.46V19l4 2v-8.54L22 3z",
  search: "M21 21l-6-6m2-5a7 7 0 1 1-14 0 7 7 0 0 1 14 0z",
  'file-text': "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6M16 13H8M16 17H8M10 9H8",
  'skip-forward': "M5 4l10 8-10 8V4zM19 5v14",
  'more-horizontal': "M12 13a1 1 0 1 0 0-2 1 1 0 0 0 0 2zM19 13a1 1 0 1 0 0-2 1 1 0 0 0 0 2zM5 13a1 1 0 1 0 0-2 1 1 0 0 0 0 2z",
  package: "M12 2l9 4.9V17L12 22l-9-4.9V7zM12 2v20M2.5 7l9.5 5 9.5-5",
  'check-circle': "M22 11.08V12a10 10 0 1 1-5.93-9.14M22 4L12 14.01l-3-3",
  'info': "M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10zM12 8h.01M12 12v4",
  'folder-open': "M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z",
  'refresh-cw': "M23 4v6h-6M1 20v-6h6M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15",
};

function Icon({ name, size = 14, style }) {
  const d = ICONS[name];
  if (!d) return null;
  return (
    React.createElement('svg', {
      width: size, height: size,
      viewBox: "0 0 24 24",
      fill: "none",
      stroke: "currentColor",
      strokeWidth: 1.75,
      strokeLinecap: "round",
      strokeLinejoin: "round",
      style: { flexShrink: 0, ...style }
    },
      React.createElement('path', { d })
    )
  );
}

function Badge({ status, needsCheck }) {
  if (needsCheck) {
    return React.createElement('span', { className: 'badge badge-check' },
      React.createElement('span', { className: 'badge-dot' }),
      'Needs check'
    );
  }
  const map = {
    pending:    ['badge-pending',    'Pending'],
    accepted:   ['badge-accepted',   'Accepted'],
    rejected:   ['badge-rejected',   'Rejected'],
    active:     ['badge-active',     'Active'],
    superseded: ['badge-superseded', 'Superseded'],
    complete:   ['badge-accepted',   'Complete'],
  };
  const [cls, label] = map[status] || ['badge-neutral', status];
  return React.createElement('span', { className: `badge ${cls}` },
    React.createElement('span', { className: 'badge-dot' }),
    label
  );
}

function Kbd({ children }) {
  return React.createElement('kbd', { className: 'kbd' }, children);
}

function Nav({ current, navigate }) {
  const { project } = window.SCOPEDATA;
  const pending = project.stats.pending;

  const links = [
    { id: 'overview',     icon: 'home',          label: 'Overview' },
    { id: 'changes',      icon: 'check-square',  label: 'Review Changes', badge: pending },
    { id: 'sheets',       icon: 'layers',        label: 'Drawings' },
    { id: 'conformed',    icon: 'grid',          label: 'Latest Set' },
    { id: 'export',       icon: 'download',      label: 'Export Workbook' },
  ];

  return React.createElement('nav', { className: 'nav' },
    // Brand
    React.createElement('div', { className: 'nav-brand' },
      React.createElement('div', { className: 'nav-brand-mark' },
        React.createElement(Icon, { name: 'file-text', size: 13 })
      ),
      React.createElement('div', null,
        React.createElement('div', { className: 'nav-brand-text' }, 'ScopeLedger'),
      )
    ),

    // Project context
    React.createElement('div', { className: 'nav-project' },
      React.createElement('div', { className: 'nav-project-label' }, 'Active Project'),
      React.createElement('div', { className: 'nav-project-name' }, project.name),
      React.createElement('div', { className: 'nav-project-pkg' },
        React.createElement('div', { className: 'nav-pkg-dot' }),
        React.createElement('span', { className: 'nav-pkg-label' },
          project.currentPackage, ' · ', project.packageDate
        )
      )
    ),

    // Nav links
    React.createElement('div', { className: 'nav-links' },
      links.map(link =>
        React.createElement('button', {
          key: link.id,
          className: `nav-link${current === link.id ? ' active' : ''}`,
          onClick: () => navigate(link.id)
        },
          React.createElement('span', { className: 'nav-link-icon' },
            React.createElement(Icon, { name: link.icon, size: 15 })
          ),
          React.createElement('span', { className: 'nav-link-label' }, link.label),
          link.badge
            ? React.createElement('span', { className: 'nav-badge' }, link.badge)
            : null
        )
      )
    ),

    // Bottom — diagnostics
    React.createElement('div', { className: 'nav-bottom' },
      React.createElement('button', {
        className: `nav-link${current === 'diagnostics' ? ' active' : ''}`,
        onClick: () => navigate('diagnostics')
      },
        React.createElement('span', { className: 'nav-link-icon' },
          React.createElement(Icon, { name: 'wrench', size: 15 })
        ),
        React.createElement('span', { className: 'nav-link-label' }, 'Diagnostics')
      )
    )
  );
}

// Minimal shared FilterBar
function FilterBar({ search, onSearch, statusFilter, onStatusFilter, counts }) {
  const statuses = [
    { id: 'all',      label: 'All',      count: counts.all },
    { id: 'pending',  label: 'Pending',  count: counts.pending },
    { id: 'accepted', label: 'Accepted', count: counts.accepted },
    { id: 'rejected', label: 'Rejected', count: counts.rejected },
  ];
  if (counts.needsCheck) {
    statuses.push({ id: 'needsCheck', label: 'Needs check', count: counts.needsCheck });
  }

  return React.createElement('div', { className: 'filter-bar' },
    React.createElement('div', { className: 'filter-input-wrap' },
      React.createElement('span', { className: 'filter-input-icon' },
        React.createElement(Icon, { name: 'search', size: 13 })
      ),
      React.createElement('input', {
        className: 'filter-input',
        type: 'text',
        placeholder: 'Sheet, scope text…',
        value: search,
        onChange: e => onSearch(e.target.value)
      })
    ),
    React.createElement('div', { className: 'filter-toggle-group' },
      statuses.map(s =>
        React.createElement('button', {
          key: s.id,
          className: `filter-toggle${statusFilter === s.id ? ' active' : ''}`,
          onClick: () => onStatusFilter(s.id)
        },
          s.label,
          React.createElement('span', { className: 'toggle-count' }, s.count)
        )
      )
    )
  );
}

Object.assign(window, { Icon, Badge, Kbd, Nav, FilterBar });
