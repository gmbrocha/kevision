// Drawings list — flat view of all sheet versions
function Drawings({ navigate }) {
  const { sheets } = window.SCOPEDATA;
  const [search, setSearch] = React.useState('');
  const [disciplineFilter, setDisciplineFilter] = React.useState('all');
  const [showSuperseded, setShowSuperseded] = React.useState(false);

  const disciplines = ['all', 'Mechanical', 'Electrical', 'Architectural'];

  const filtered = sheets.filter(s => {
    if (!showSuperseded && s.status === 'superseded') return false;
    const matchSearch = !search ||
      s.sheet.toLowerCase().includes(search.toLowerCase()) ||
      s.title.toLowerCase().includes(search.toLowerCase());
    const matchDiscipline = disciplineFilter === 'all' || s.discipline === disciplineFilter;
    return matchSearch && matchDiscipline;
  });

  const activeCount = sheets.filter(s => s.status === 'active').length;
  const supersededCount = sheets.filter(s => s.status === 'superseded').length;

  return React.createElement('div', { className: 'page-area' },
    React.createElement('div', { className: 'page-header' },
      React.createElement('div', null,
        React.createElement('h1', { className: 'page-title' }, 'Drawings'),
        React.createElement('p', { className: 'page-subtitle' },
          `${activeCount} active sheets${supersededCount > 0 ? ` · ${supersededCount} superseded` : ''}`
        )
      ),
      React.createElement('div', { className: 'page-actions' },
        React.createElement('button', {
          className: `btn btn-sm ${showSuperseded ? 'btn-secondary' : 'btn-ghost'}`,
          onClick: () => setShowSuperseded(v => !v)
        },
          React.createElement(window.Icon, { name: 'layers', size: 12 }),
          showSuperseded ? 'Hide superseded' : 'Show superseded'
        )
      )
    ),

    React.createElement('div', { className: 'page-scroll' },
      React.createElement('div', { className: 'page-content' },
        // Filters
        React.createElement('div', { className: 'filter-bar' },
          React.createElement('div', { className: 'filter-input-wrap' },
            React.createElement('span', { className: 'filter-input-icon' },
              React.createElement(window.Icon, { name: 'search', size: 13 })
            ),
            React.createElement('input', {
              className: 'filter-input',
              type: 'text',
              placeholder: 'Sheet number or title…',
              value: search,
              onChange: e => setSearch(e.target.value)
            })
          ),
          React.createElement('div', { className: 'filter-toggle-group' },
            disciplines.map(d =>
              React.createElement('button', {
                key: d,
                className: `filter-toggle${disciplineFilter === d ? ' active' : ''}`,
                onClick: () => setDisciplineFilter(d)
              }, d === 'all' ? 'All' : d)
            )
          )
        ),

        React.createElement('div', { className: 'data-table-wrap' },
          React.createElement('table', { className: 'data-table' },
            React.createElement('thead', null,
              React.createElement('tr', null,
                React.createElement('th', null, 'Sheet'),
                React.createElement('th', null, 'Title'),
                React.createElement('th', null, 'Revision'),
                React.createElement('th', null, 'Previous'),
                React.createElement('th', null, 'Discipline'),
                React.createElement('th', { className: 'col-right' }, 'Changes'),
                React.createElement('th', null, 'Status'),
                React.createElement('th', null, '')
              )
            ),
            React.createElement('tbody', null,
              filtered.map(s =>
                React.createElement('tr', {
                  key: s.id,
                  className: 'row-link',
                  style: s.status === 'superseded' ? { opacity: 0.55 } : {},
                  onClick: () => navigate('sheet-detail', s.id)
                },
                  React.createElement('td', { className: 'cell-mono' }, s.sheet),
                  React.createElement('td', { style: { fontSize: 'var(--text-sm)' } }, s.title),
                  React.createElement('td', { className: 'cell-mono', style: { color: 'var(--accent-text)' } }, s.rev),
                  React.createElement('td', { className: 'cell-mono cell-dim' }, s.prevRev),
                  React.createElement('td', { className: 'cell-secondary', style: { fontSize: 'var(--text-sm)' } }, s.discipline),
                  React.createElement('td', { className: 'col-right cell-mono' },
                    s.changes > 0
                      ? React.createElement('span', { style: { color: 'var(--accent-text)' } }, s.changes)
                      : React.createElement('span', { style: { color: 'var(--text-tertiary)' } }, '—')
                  ),
                  React.createElement('td', null,
                    React.createElement('div', { style: { display: 'flex', gap: 6, alignItems: 'center' } },
                      React.createElement(window.Badge, { status: s.status }),
                      s.warnings > 0 && React.createElement('span', {
                        style: { display: 'flex', alignItems: 'center', gap: 4, fontSize: 'var(--text-xs)', color: 'var(--status-check)', fontFamily: 'var(--font-mono)' }
                      },
                        React.createElement(window.Icon, { name: 'alert-triangle', size: 11 }),
                        s.warnings
                      )
                    )
                  ),
                  React.createElement('td', { className: 'col-right' },
                    React.createElement('button', {
                      className: 'btn btn-ghost btn-sm',
                      onClick: e => { e.stopPropagation(); navigate('sheet-detail', s.id); }
                    }, 'View →')
                  )
                )
              )
            )
          )
        )
      )
    )
  );
}

Object.assign(window, { Drawings });
