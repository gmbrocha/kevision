// Review Changes — the queue Kevin lives on
function ReviewChanges({ navigate }) {
  const { changes, project } = window.SCOPEDATA;
  const [search, setSearch] = React.useState('');
  const [statusFilter, setStatusFilter] = React.useState('all');
  const [selected, setSelected] = React.useState(new Set());

  const filtered = changes.filter(c => {
    const matchSearch = !search ||
      c.sheet.toLowerCase().includes(search.toLowerCase()) ||
      c.scope.toLowerCase().includes(search.toLowerCase()) ||
      c.title.toLowerCase().includes(search.toLowerCase());
    const matchStatus = statusFilter === 'all' ||
      (statusFilter === 'needsCheck' ? c.needsCheck : c.status === statusFilter);
    return matchSearch && matchStatus;
  });

  const counts = {
    all: changes.length,
    pending: changes.filter(c => c.status === 'pending').length,
    accepted: changes.filter(c => c.status === 'accepted').length,
    rejected: changes.filter(c => c.status === 'rejected').length,
    needsCheck: changes.filter(c => c.needsCheck).length,
  };

  // First pending change in the full list (for "next up" highlight)
  const firstPendingId = changes.find(c => c.status === 'pending')?.id;

  const toggleSelect = (id, e) => {
    e.stopPropagation();
    const next = new Set(selected);
    if (next.has(id)) next.delete(id); else next.add(id);
    setSelected(next);
  };

  const allVisibleSelected = filtered.length > 0 && filtered.every(c => selected.has(c.id));
  const toggleAll = () => {
    if (allVisibleSelected) setSelected(new Set());
    else setSelected(new Set(filtered.map(c => c.id)));
  };

  return React.createElement('div', { className: 'page-area' },
    // Header
    React.createElement('div', { className: 'page-header' },
      React.createElement('div', null,
        React.createElement('h1', { className: 'page-title' }, 'Review Changes'),
        React.createElement('p', { className: 'page-subtitle' },
          project.currentPackage, ' · ', project.packageDate,
          ' · ', counts.pending, ' pending'
        )
      ),
      React.createElement('div', { className: 'page-actions' },
        selected.size > 0 && React.createElement(React.Fragment, null,
          React.createElement('span', {
            style: { fontSize: 'var(--text-sm)', color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }
          }, `${selected.size} selected`),
          React.createElement('button', { className: 'btn btn-accept btn-sm' },
            React.createElement(window.Icon, { name: 'check', size: 12 }), 'Accept all'
          ),
          React.createElement('button', { className: 'btn btn-danger btn-sm' },
            React.createElement(window.Icon, { name: 'x', size: 12 }), 'Reject all'
          ),
          React.createElement('div', { style: { width: 1, height: 20, background: 'var(--rule-hairline)' } })
        ),
        // Jump to next pending
        counts.pending > 0 && React.createElement('button', {
          className: 'btn btn-primary',
          onClick: () => {
            const nextPending = changes.find(c => c.status === 'pending');
            if (nextPending) navigate('change-detail', nextPending.id);
          }
        },
          React.createElement(window.Icon, { name: 'skip-forward', size: 14 }),
          'Start reviewing'
        )
      )
    ),

    React.createElement('div', { className: 'page-scroll' },
      React.createElement('div', { className: 'page-content' },

        // Filter bar
        React.createElement(window.FilterBar, {
          search, onSearch: setSearch,
          statusFilter, onStatusFilter: setStatusFilter,
          counts
        }),

        // "Needs check" callout
        counts.needsCheck > 0 && statusFilter === 'all' && React.createElement('div', { className: 'callout callout-check' },
          React.createElement(window.Icon, { name: 'alert-triangle', size: 15, style: { flexShrink: 0, marginTop: 1 } }),
          React.createElement('div', null,
            React.createElement('strong', null, `${counts.needsCheck} drawing${counts.needsCheck > 1 ? 's' : ''} need manual check`),
            ' — scope text was extracted from rasterized PDF. Review carefully before accepting.'
          )
        ),

        // Table
        React.createElement('div', { className: 'data-table-wrap' },
          React.createElement('table', { className: 'data-table' },
            React.createElement('thead', null,
              React.createElement('tr', null,
                React.createElement('th', { style: { width: 32 } },
                  React.createElement('input', {
                    type: 'checkbox',
                    checked: allVisibleSelected,
                    onChange: toggleAll,
                    style: { accentColor: 'var(--accent)', cursor: 'pointer' }
                  })
                ),
                React.createElement('th', null, 'Sheet'),
                React.createElement('th', null, 'Cloud'),
                React.createElement('th', null, 'Scope of change'),
                React.createElement('th', null, 'Discipline'),
                React.createElement('th', null, 'Status'),
                React.createElement('th', null, '')
              )
            ),
            React.createElement('tbody', null,
              filtered.length === 0
                ? React.createElement('tr', null,
                    React.createElement('td', { colSpan: 7, className: 'data-table-empty' },
                      'No changes match this filter'
                    )
                  )
                : filtered.map((c, i) => {
                    const isNextUp = c.id === firstPendingId && statusFilter !== 'accepted' && statusFilter !== 'rejected';
                    return React.createElement('tr', {
                      key: c.id,
                      className: [
                        'row-link',
                        isNextUp ? 'row-next-up' : '',
                        c.needsCheck ? 'row-needs-check' : ''
                      ].filter(Boolean).join(' '),
                      onClick: () => navigate('change-detail', c.id)
                    },
                      React.createElement('td', { onClick: e => e.stopPropagation() },
                        React.createElement('input', {
                          type: 'checkbox',
                          checked: selected.has(c.id),
                          onChange: e => toggleSelect(c.id, e),
                          style: { accentColor: 'var(--accent)', cursor: 'pointer' }
                        })
                      ),
                      React.createElement('td', { className: 'cell-mono' },
                        React.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: 8 } },
                          isNextUp && React.createElement('div', { className: 'next-up-callout' }, 'Next'),
                          c.sheet
                        )
                      ),
                      React.createElement('td', { className: 'cell-mono', style: { color: 'var(--accent-text)' } }, c.cloud),
                      React.createElement('td', { style: { maxWidth: 360 } },
                        React.createElement('div', {
                          style: {
                            fontSize: 'var(--text-sm)',
                            color: 'var(--text-primary)',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                            maxWidth: 360
                          }
                        }, c.scope)
                      ),
                      React.createElement('td', { className: 'cell-secondary', style: { fontSize: 'var(--text-sm)', whiteSpace: 'nowrap' } },
                        c.discipline
                      ),
                      React.createElement('td', null,
                        React.createElement('div', { style: { display: 'flex', gap: 6, alignItems: 'center' } },
                          React.createElement(window.Badge, { status: c.status }),
                          c.needsCheck && React.createElement(window.Badge, { needsCheck: true })
                        )
                      ),
                      React.createElement('td', { className: 'col-right' },
                        React.createElement('button', {
                          className: 'btn btn-ghost btn-sm',
                          onClick: e => { e.stopPropagation(); navigate('change-detail', c.id); }
                        }, 'Review →')
                      )
                    );
                  })
            )
          )
        )
      )
    )
  );
}

Object.assign(window, { ReviewChanges });
