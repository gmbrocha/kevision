// Sheet Detail — full sheet image with bbox overlays + version chain
function SheetDetail({ sheetId, navigate }) {
  const { sheets, changes } = window.SCOPEDATA;
  const sheet = sheets.find(s => s.id === sheetId) || sheets[2]; // default M-201

  const sheetChanges = changes.filter(c => c.sheet === sheet.sheet && c.rev === sheet.rev);

  // Version chain: all versions of this sheet number
  const versions = sheets.filter(s => s.sheet === sheet.sheet)
    .sort((a, b) => b.rev.localeCompare(a.rev));

  // Fake bbox positions for demo (as % of image)
  const bboxes = sheetChanges.map((c, i) => ({
    ...c,
    x: 15 + i * 30,
    y: 20 + (i % 2) * 35,
    w: 22,
    h: 18
  }));

  return React.createElement('div', {
    style: { display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }
  },
    // Header
    React.createElement('div', { className: 'page-header' },
      React.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: 12 } },
        React.createElement('button', {
          className: 'cockpit-back',
          onClick: () => navigate('sheets')
        },
          React.createElement(window.Icon, { name: 'arrow-left', size: 14 }),
          'Drawings'
        ),
        React.createElement('div', { style: { width: 1, height: 20, background: 'var(--rule-hairline)' } }),
        React.createElement('div', null,
          React.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: 10 } },
            React.createElement('span', { style: { fontFamily: 'var(--font-mono)', fontSize: 'var(--text-lg)', fontWeight: 600, color: 'var(--text-primary)' } }, sheet.sheet),
            React.createElement(window.Badge, { status: sheet.status })
          ),
          React.createElement('p', { className: 'page-subtitle', style: { marginTop: 2 } }, sheet.title)
        )
      ),
      React.createElement('div', { className: 'page-actions' },
        React.createElement('span', { style: { fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)' } },
          sheet.rev, ' → ', sheet.prevRev
        ),
        sheetChanges.length > 0 && React.createElement('button', {
          className: 'btn btn-primary btn-sm',
          onClick: () => navigate('change-detail', sheetChanges[0].id)
        },
          React.createElement(window.Icon, { name: 'check-square', size: 12 }),
          `Review ${sheetChanges.length} change${sheetChanges.length > 1 ? 's' : ''}`
        )
      )
    ),

    // Main — image + sidebar
    React.createElement('div', { style: { display: 'grid', gridTemplateColumns: '1fr 280px', flex: 1, overflow: 'hidden' } },

      // Sheet image with bbox overlays
      React.createElement('div', { className: 'sheet-image-area' },
        React.createElement('div', {
          style: { display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', position: 'relative', zIndex: 1 }
        },
          React.createElement('div', { className: 'sheet-img-inner' },
            React.createElement('img', {
              src: `https://placehold.co/900x640/0d0c0a/1e1d1a?text=${encodeURIComponent(sheet.sheet + ' — ' + sheet.rev)}`,
              alt: sheet.sheet,
              style: { display: 'block', maxHeight: 'calc(100vh - 160px)', maxWidth: '100%', border: '1px solid var(--rule-hairline)' }
            }),
            // Bboxes
            bboxes.map(b =>
              React.createElement('div', {
                key: b.id,
                className: 'bbox',
                style: {
                  left: b.x + '%',
                  top: b.y + '%',
                  width: b.w + '%',
                  height: b.h + '%'
                },
                onClick: () => navigate('change-detail', b.id),
                title: `Cloud ${b.cloud} — ${b.scope.slice(0, 60)}…`
              },
                React.createElement('div', { className: 'bbox-label' }, `Cloud ${b.cloud}`)
              )
            )
          )
        )
      ),

      // Sidebar
      React.createElement('div', { className: 'sheet-sidebar' },

        // Version chain
        React.createElement('div', { className: 'sheet-version-chain' },
          React.createElement('div', { className: 'version-chain-title' }, 'Version chain'),
          versions.map((v, i) =>
            React.createElement('div', { key: v.id, className: 'version-item' },
              React.createElement('div', { className: `version-dot${i === 0 ? ' current' : ' superseded'}` }),
              React.createElement('div', { className: 'version-info' },
                React.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: 8 } },
                  React.createElement('span', { className: 'version-rev' }, v.rev),
                  i === 0 && React.createElement(window.Badge, { status: 'active' })
                ),
                React.createElement('div', { className: 'version-date' },
                  `${v.changes} change${v.changes !== 1 ? 's' : ''} detected`
                ),
                i === 0 && React.createElement('button', {
                  className: 'btn btn-ghost btn-sm',
                  style: { marginTop: 6, paddingLeft: 0 },
                  onClick: () => navigate('sheet-detail', v.id)
                }, 'Current (viewing)')
              )
            )
          )
        ),

        // Changes on this sheet
        React.createElement('div', { style: { padding: 'var(--sp-5)', flex: 1 } },
          React.createElement('div', { className: 'version-chain-title', style: { marginBottom: 'var(--sp-3)' } },
            `Changes — ${sheet.rev}`
          ),
          sheetChanges.length === 0
            ? React.createElement('p', { style: { fontSize: 'var(--text-sm)', color: 'var(--text-tertiary)' } },
                'No changes detected on this sheet.'
              )
            : sheetChanges.map(c =>
                React.createElement('div', {
                  key: c.id,
                  style: {
                    padding: 'var(--sp-3)',
                    background: 'var(--surface-raised)',
                    border: '1px solid var(--rule-hairline)',
                    borderRadius: 'var(--radius-md)',
                    marginBottom: 'var(--sp-2)',
                    cursor: 'pointer',
                    transition: 'border-color var(--dur-fast)'
                  },
                  onClick: () => navigate('change-detail', c.id)
                },
                  React.createElement('div', { style: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 } },
                    React.createElement('span', { style: { fontFamily: 'var(--font-mono)', fontSize: 'var(--text-sm)', color: 'var(--accent-text)' } },
                      `Cloud ${c.cloud}`
                    ),
                    React.createElement(window.Badge, { status: c.status })
                  ),
                  React.createElement('p', { style: { fontSize: 'var(--text-xs)', color: 'var(--text-secondary)', lineHeight: 'var(--leading-snug)' } },
                    c.scope.length > 90 ? c.scope.slice(0, 90) + '…' : c.scope
                  )
                )
              )
        )
      )
    )
  );
}

Object.assign(window, { SheetDetail });
