// Latest Set — drawing index, conformed set view
function LatestSet({ navigate }) {
  const { conformedSheets } = window.SCOPEDATA;
  const [search, setSearch] = React.useState('');
  const [showRevisedOnly, setShowRevisedOnly] = React.useState(false);

  const filtered = conformedSheets.filter(s => {
    if (showRevisedOnly && !s.revised) return false;
    return !search ||
      s.sheet.toLowerCase().includes(search.toLowerCase()) ||
      s.title.toLowerCase().includes(search.toLowerCase());
  });

  const revisedCount = conformedSheets.filter(s => s.revised).length;

  return React.createElement('div', { className: 'page-area' },
    React.createElement('div', { className: 'page-header' },
      React.createElement('div', null,
        React.createElement('h1', { className: 'page-title' }, 'Latest Set'),
        React.createElement('p', { className: 'page-subtitle' },
          `${conformedSheets.length} drawings · ${revisedCount} revised in current package`
        )
      ),
      React.createElement('div', { className: 'page-actions' },
        React.createElement('div', { className: 'filter-input-wrap', style: { maxWidth: 220 } },
          React.createElement('span', { className: 'filter-input-icon' },
            React.createElement(window.Icon, { name: 'search', size: 13 })
          ),
          React.createElement('input', {
            className: 'filter-input',
            type: 'text',
            placeholder: 'Sheet number…',
            value: search,
            onChange: e => setSearch(e.target.value)
          })
        ),
        React.createElement('button', {
          className: `btn btn-sm ${showRevisedOnly ? 'btn-secondary' : 'btn-ghost'}`,
          onClick: () => setShowRevisedOnly(v => !v)
        },
          showRevisedOnly ? 'Revised only' : 'All sheets'
        )
      )
    ),

    React.createElement('div', { className: 'page-scroll' },
      React.createElement('div', { className: 'page-content' },
        React.createElement('div', { className: 'callout callout-info' },
          React.createElement(window.Icon, { name: 'info', size: 14, style: { flexShrink: 0 } }),
          React.createElement('span', null,
            'For each drawing number, this shows the latest version the tool detected and what it supersedes. Verify the correct revision was picked up before exporting.'
          )
        ),

        React.createElement('div', { className: 'conformed-grid' },
          filtered.map(s =>
            React.createElement('div', {
              key: s.sheet,
              className: `conformed-card${s.revised ? ' revised' : ''}`,
              onClick: () => {
                const found = window.SCOPEDATA.sheets.find(sh => sh.sheet === s.sheet && sh.status === 'active');
                if (found) navigate('sheet-detail', found.id);
              }
            },
              // Thumbnail
              React.createElement('div', { className: 'conformed-thumb' },
                React.createElement('div', { className: 'conformed-thumb-placeholder' }),
                React.createElement('img', {
                  src: `https://placehold.co/360x220/111009/1e1d1a?text=${encodeURIComponent(s.sheet)}`,
                  alt: s.sheet,
                  style: { position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', opacity: 0.5 }
                }),
                s.revised && React.createElement('div', { className: 'conformed-revised-flag' }, 'Revised')
              ),

              // Info
              React.createElement('div', { className: 'conformed-card-info' },
                React.createElement('div', { className: 'conformed-sheet-id' }, s.sheet),
                React.createElement('div', { className: 'conformed-sheet-title' }, s.title),
                React.createElement('div', { className: 'conformed-sheet-chain' },
                  React.createElement('span', { style: { color: 'var(--accent-text)', fontWeight: 500 } }, s.currentRev),
                  s.prevRev && React.createElement(React.Fragment, null,
                    React.createElement('span', { className: 'arrow' }, '←'),
                    React.createElement('span', null, s.prevRev)
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

Object.assign(window, { LatestSet });
