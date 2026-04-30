// Export Workbook page
function ExportPage({ navigate }) {
  const { project, exportHistory } = window.SCOPEDATA;
  const { stats } = project;
  const totalReviewed = stats.accepted + stats.rejected;
  const totalChanges = stats.pending + stats.accepted + stats.rejected;
  const pctComplete = Math.round((totalReviewed / totalChanges) * 100);
  const [generating, setGenerating] = React.useState(false);
  const [generated, setGenerated] = React.useState(false);

  const handleGenerate = () => {
    setGenerating(true);
    setTimeout(() => { setGenerating(false); setGenerated(true); }, 1800);
  };

  const outputFiles = [
    { name: `ScopeLedger_Rev04_${new Date().toISOString().slice(0,10).replace(/-/g,'')}.xlsx`, desc: 'Excel workbook — contractor pricing deliverable', icon: 'file-down', primary: true },
    { name: 'changes_Rev04.csv', desc: 'Change item export — all fields, UTF-8', icon: 'file-text', primary: false },
    { name: 'review_packet_Rev04.pdf', desc: 'Review packet — crops + decisions + notes', icon: 'file-text', primary: false },
  ];

  return React.createElement('div', { className: 'page-area' },
    React.createElement('div', { className: 'page-header' },
      React.createElement('div', null,
        React.createElement('h1', { className: 'page-title' }, 'Export Workbook'),
        React.createElement('p', { className: 'page-subtitle' },
          project.currentPackage, ' · ', project.packageDate
        )
      ),
      React.createElement('div', { className: 'page-actions' },
        React.createElement('button', {
          className: 'btn btn-secondary btn-sm',
          onClick: () => window.open(project.driveFolder, '_blank')
        },
          React.createElement(window.Icon, { name: 'folder-open', size: 13 }),
          'Open Drive folder'
        )
      )
    ),

    React.createElement('div', { className: 'page-scroll' },
      React.createElement('div', { className: 'page-content' },
        React.createElement('div', { className: 'export-layout' },

          // Readiness panel
          React.createElement('div', { className: 'panel' },
            React.createElement('div', { className: 'panel-header' },
              React.createElement('span', { className: 'panel-title' }, 'Review status')
            ),
            React.createElement('div', { className: 'panel-body', style: { display: 'flex', flexDirection: 'column', gap: 'var(--sp-4)' } },

              React.createElement('div', { className: 'stat-row', style: { border: 'none', gap: 'var(--sp-4)' } },
                [
                  { label: 'Accepted', value: stats.accepted, cls: 'accepted' },
                  { label: 'Rejected', value: stats.rejected, cls: 'rejected' },
                  { label: 'Pending', value: stats.pending,  cls: stats.pending > 0 ? 'pending' : '' },
                ].map(s => React.createElement('div', { key: s.label, style: { flex: 1, display: 'flex', flexDirection: 'column', gap: 4 } },
                  React.createElement('span', { className: `stat-value ${s.cls}`, style: { fontSize: 'var(--text-2xl)' } }, s.value),
                  React.createElement('span', { className: 'stat-label' }, s.label)
                ))
              ),

              React.createElement('div', null,
                React.createElement('div', { className: 'export-readiness-label' }, 'Review completion'),
                React.createElement('div', { className: 'progress-bar-track', style: { marginTop: 6 } },
                  React.createElement('div', {
                    className: `progress-bar-fill${pctComplete === 100 ? ' complete' : ''}`,
                    style: { width: pctComplete + '%' }
                  })
                ),
                React.createElement('div', { className: 'progress-label', style: { marginTop: 4 } },
                  stats.pending > 0
                    ? `${stats.pending} changes still pending — they will export with "Pending" status`
                    : 'All changes reviewed'
                )
              ),

              stats.pending > 0 && React.createElement('div', { className: 'callout callout-check' },
                React.createElement(window.Icon, { name: 'alert-triangle', size: 14, style: { flexShrink: 0 } }),
                React.createElement('span', null,
                  `${stats.pending} pending changes will be included in the workbook as-is. `,
                  React.createElement('button', {
                    className: 'btn btn-ghost btn-sm',
                    style: { display: 'inline-flex', marginLeft: 4 },
                    onClick: () => navigate('changes')
                  }, 'Finish reviewing →')
                )
              )
            )
          ),

          // Generate panel
          React.createElement('div', { className: 'panel' },
            React.createElement('div', { className: 'panel-header' },
              React.createElement('span', { className: 'panel-title' }, 'Generate'),
            ),
            React.createElement('div', { className: 'panel-body', style: { display: 'flex', flexDirection: 'column', gap: 'var(--sp-4)' } },

              // Output files list
              outputFiles.map(f =>
                React.createElement('div', {
                  key: f.name,
                  style: {
                    display: 'flex',
                    alignItems: 'center',
                    gap: 'var(--sp-3)',
                    padding: 'var(--sp-3)',
                    background: 'var(--surface-raised)',
                    border: '1px solid var(--rule-hairline)',
                    borderRadius: 'var(--radius-md)',
                    opacity: generated ? 1 : 0.5,
                    transition: 'opacity var(--dur-normal)'
                  }
                },
                  React.createElement(window.Icon, { name: f.icon, size: 16, style: { color: generated ? 'var(--accent-text)' : 'var(--text-tertiary)', flexShrink: 0 } }),
                  React.createElement('div', { style: { flex: 1, minWidth: 0 } },
                    React.createElement('div', { style: { fontFamily: 'var(--font-mono)', fontSize: 'var(--text-sm)', color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } }, f.name),
                    React.createElement('div', { style: { fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', marginTop: 2 } }, f.desc)
                  ),
                  generated && React.createElement('button', { className: 'btn btn-secondary btn-sm' },
                    React.createElement(window.Icon, { name: 'download', size: 12 }), 'Save'
                  )
                )
              ),

              // Generate button
              React.createElement('button', {
                className: `btn btn-xl ${generated ? 'btn-secondary' : 'btn-primary'}`,
                style: { width: '100%', justifyContent: 'center' },
                onClick: handleGenerate,
                disabled: generating
              },
                generating
                  ? React.createElement(React.Fragment, null,
                      React.createElement(window.Icon, { name: 'refresh-cw', size: 18, style: { animation: 'spin 1s linear infinite' } }),
                      'Generating…'
                    )
                  : generated
                  ? React.createElement(React.Fragment, null,
                      React.createElement(window.Icon, { name: 'refresh-cw', size: 18 }),
                      'Re-generate workbook'
                    )
                  : React.createElement(React.Fragment, null,
                      React.createElement(window.Icon, { name: 'download', size: 18 }),
                      'Generate workbook'
                    )
              )
            )
          ),

          // Export history
          exportHistory.length > 0 && React.createElement('div', { className: 'panel' },
            React.createElement('div', { className: 'panel-header' },
              React.createElement('span', { className: 'panel-title' }, 'Export history')
            ),
            React.createElement('div', { className: 'data-table-wrap', style: { border: 'none', borderRadius: 0 } },
              React.createElement('table', { className: 'data-table' },
                React.createElement('thead', null,
                  React.createElement('tr', null,
                    React.createElement('th', null, 'Package'),
                    React.createElement('th', null, 'Generated'),
                    React.createElement('th', { className: 'col-right' }, 'Accepted'),
                    React.createElement('th', { className: 'col-right' }, 'Rejected'),
                    React.createElement('th', null, 'Files'),
                    React.createElement('th', null, '')
                  )
                ),
                React.createElement('tbody', null,
                  exportHistory.map(ex =>
                    React.createElement('tr', { key: ex.id },
                      React.createElement('td', { className: 'cell-mono' }, ex.package),
                      React.createElement('td', { className: 'cell-secondary', style: { fontSize: 'var(--text-sm)', fontFamily: 'var(--font-mono)' } }, ex.timestamp),
                      React.createElement('td', { className: 'col-right cell-mono', style: { color: 'var(--status-accepted)' } }, ex.accepted),
                      React.createElement('td', { className: 'col-right cell-mono', style: { color: 'var(--status-rejected)' } }, ex.rejected),
                      React.createElement('td', { style: { fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)' } },
                        ex.files.join(', ')
                      ),
                      React.createElement('td', { className: 'col-right' },
                        React.createElement('button', { className: 'btn btn-ghost btn-sm' },
                          React.createElement(window.Icon, { name: 'download', size: 12 }), 'Re-download'
                        )
                      )
                    )
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

Object.assign(window, { ExportPage });
