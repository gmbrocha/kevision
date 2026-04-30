// Diagnostics — quiet utility page
function Diagnostics({ navigate }) {
  const { diagnostics } = window.SCOPEDATA;
  const totalIssues = diagnostics.reduce((n, d) => n + d.issues.length, 0);

  return React.createElement('div', { className: 'page-area' },
    React.createElement('div', { className: 'page-header' },
      React.createElement('div', null,
        React.createElement('h1', { className: 'page-title' }, 'Diagnostics'),
        React.createElement('p', { className: 'page-subtitle' },
          'PDF health and ingestion status — not part of the review workflow'
        )
      ),
      totalIssues === 0 && React.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: 8, fontSize: 'var(--text-sm)', color: 'var(--status-accepted)', fontFamily: 'var(--font-mono)' } },
        React.createElement(window.Icon, { name: 'check-circle', size: 14 }),
        'All files healthy'
      )
    ),

    React.createElement('div', { className: 'page-scroll' },
      React.createElement('div', { className: 'page-content' },
        totalIssues > 0 && React.createElement('div', { className: 'callout callout-check' },
          React.createElement(window.Icon, { name: 'alert-triangle', size: 14, style: { flexShrink: 0 } }),
          React.createElement('span', null,
            `${totalIssues} issue${totalIssues > 1 ? 's' : ''} detected across ingested PDFs. Review before accepting affected changes.`
          )
        ),

        React.createElement('div', { className: 'panel' },
          React.createElement('div', { className: 'panel-header' },
            React.createElement('span', { className: 'panel-title' }, 'Ingested PDF files')
          ),
          React.createElement('div', { className: 'data-table-wrap', style: { border: 'none', borderRadius: 0 } },
            React.createElement('table', { className: 'data-table diag-table' },
              React.createElement('thead', null,
                React.createElement('tr', null,
                  React.createElement('th', null, 'File'),
                  React.createElement('th', { className: 'col-right' }, 'Pages'),
                  React.createElement('th', { className: 'col-right' }, 'Size'),
                  React.createElement('th', { className: 'col-right' }, 'Clouds'),
                  React.createElement('th', null, 'Text layer'),
                  React.createElement('th', null, 'Issues')
                )
              ),
              React.createElement('tbody', null,
                diagnostics.map(d =>
                  React.createElement('tr', { key: d.file },
                    React.createElement('td', { style: { fontFamily: 'var(--font-mono)', fontSize: 'var(--text-sm)' } }, d.file),
                    React.createElement('td', { className: 'col-right cell-mono' }, d.pages),
                    React.createElement('td', { className: 'col-right cell-mono' }, d.sizeMb + ' MB'),
                    React.createElement('td', { className: 'col-right cell-mono', style: { color: 'var(--accent-text)' } }, d.clouds),
                    React.createElement('td', null,
                      d.vectorText
                        ? React.createElement('span', { className: 'diag-ok' }, 'Vector')
                        : React.createElement('span', { style: { color: 'var(--status-check)', fontSize: 'var(--text-sm)', display: 'flex', alignItems: 'center', gap: 5 } },
                            React.createElement(window.Icon, { name: 'alert-triangle', size: 12 }),
                            'Rasterized — OCR'
                          )
                    ),
                    React.createElement('td', null,
                      d.issues.length === 0
                        ? React.createElement('span', { className: 'diag-ok' }, '—')
                        : d.issues.map((iss, i) =>
                            React.createElement('div', { key: i, className: 'diag-issue' },
                              React.createElement(window.Icon, { name: 'alert-triangle', size: 12, style: { flexShrink: 0, marginTop: 2 } }),
                              iss
                            )
                          )
                    )
                  )
                )
              )
            )
          )
        ),

        // Summary counts
        React.createElement('div', { className: 'panel' },
          React.createElement('div', { className: 'panel-header' },
            React.createElement('span', { className: 'panel-title' }, 'Ingestion summary')
          ),
          React.createElement('div', { className: 'panel-body' },
            React.createElement('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 'var(--sp-4)' } },
              [
                { label: 'Total PDFs',    value: diagnostics.length },
                { label: 'Total pages',   value: diagnostics.reduce((n, d) => n + d.pages, 0) },
                { label: 'Total clouds',  value: diagnostics.reduce((n, d) => n + d.clouds, 0) },
                { label: 'Rasterized',    value: diagnostics.filter(d => !d.vectorText).length },
              ].map(s =>
                React.createElement('div', { key: s.label },
                  React.createElement('div', { style: { fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xl)', fontWeight: 600, color: 'var(--text-primary)' } }, s.value),
                  React.createElement('div', { className: 'stat-label' }, s.label)
                )
              )
            )
          )
        )
      )
    )
  );
}

Object.assign(window, { Diagnostics });
