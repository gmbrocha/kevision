// Project Overview — one-glance landing page
function Overview({ navigate }) {
  const { project, revisionPackages, changes } = window.SCOPEDATA;
  const { stats } = project;
  const totalReviewed = stats.accepted + stats.rejected;
  const totalChanges = stats.pending + stats.accepted + stats.rejected;
  const pctComplete = Math.round((totalReviewed / totalChanges) * 100);
  const nextPending = changes.find(c => c.status === 'pending');

  return React.createElement('div', { className: 'page-area' },
    // Hero — project name + primary CTA
    React.createElement('div', { className: 'overview-hero' },
      React.createElement('div', { className: 'overview-hero-left' },
        React.createElement('h1', { className: 'overview-project-title' }, project.name),
        React.createElement('p', { className: 'overview-project-subtitle' }, project.subtitle),
        React.createElement('div', { className: 'overview-pkg-chip' },
          React.createElement('span', { className: 'nav-pkg-dot' }),
          React.createElement('span', null, 'Active package:'),
          React.createElement('span', { className: 'pkg-name' }, ' ' + project.currentPackage),
          React.createElement('span', { style: { color: 'var(--text-tertiary)' } }, ' · ingested ' + project.packageDate)
        )
      ),
      stats.pending > 0
        ? React.createElement('button', {
            className: 'btn btn-primary btn-xl',
            onClick: () => nextPending && navigate('change-detail', nextPending.id)
          },
            React.createElement(window.Icon, { name: 'skip-forward', size: 18 }),
            `Review next — ${stats.pending} pending`
          )
        : React.createElement('button', {
            className: 'btn btn-primary btn-xl',
            onClick: () => navigate('export')
          },
            React.createElement(window.Icon, { name: 'download', size: 18 }),
            'Export workbook'
          )
    ),

    React.createElement('div', { className: 'page-scroll' },
      React.createElement('div', { className: 'page-content' },

        // Review progress strip — the ONLY stat block
        React.createElement('div', { className: 'stat-row' },
          React.createElement('div', { className: 'stat-block' },
            React.createElement('span', { className: `stat-value ${stats.pending > 0 ? 'pending' : 'accepted'}` },
              stats.pending
            ),
            React.createElement('span', { className: 'stat-label' }, 'Pending review')
          ),
          React.createElement('div', { className: 'stat-block' },
            React.createElement('span', { className: 'stat-value accepted' }, stats.accepted),
            React.createElement('span', { className: 'stat-label' }, 'Accepted')
          ),
          React.createElement('div', { className: 'stat-block' },
            React.createElement('span', { className: 'stat-value rejected' }, stats.rejected),
            React.createElement('span', { className: 'stat-label' }, 'Rejected')
          ),
          React.createElement('div', { className: 'stat-block' },
            React.createElement('span', { className: `stat-value ${stats.needsCheck > 0 ? 'check' : ''}` },
              stats.needsCheck
            ),
            React.createElement('span', { className: 'stat-label' }, 'Needs check')
          ),
          // Progress col
          React.createElement('div', {
            className: 'stat-block',
            style: { flex: 2, justifyContent: 'center', gap: 8 }
          },
            React.createElement('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' } },
              React.createElement('span', { className: 'stat-label' }, 'Review progress'),
              React.createElement('span', { className: 'stat-value', style: { fontSize: 'var(--text-xl)' } },
                pctComplete + '%'
              )
            ),
            React.createElement('div', { className: 'progress-bar-track', style: { height: 6 } },
              React.createElement('div', {
                className: `progress-bar-fill${pctComplete === 100 ? ' complete' : ''}`,
                style: { width: pctComplete + '%' }
              })
            ),
            React.createElement('div', { className: 'progress-label' },
              `${totalReviewed} of ${totalChanges} changes reviewed`
            )
          )
        ),

        // Needs-check callout
        stats.needsCheck > 0 && React.createElement('div', { className: 'callout callout-check' },
          React.createElement(window.Icon, { name: 'alert-triangle', size: 15, style: { flexShrink: 0 } }),
          React.createElement('div', null,
            React.createElement('strong', null, `${stats.needsCheck} change${stats.needsCheck > 1 ? 's' : ''} flagged for manual check`),
            ' — extracted from rasterized PDF. Review scope text before accepting. ',
            React.createElement('button', {
              className: 'btn btn-ghost btn-sm',
              style: { display: 'inline-flex', marginLeft: 4 },
              onClick: () => navigate('changes')
            }, 'View in queue →')
          )
        ),

        // Revision packages
        React.createElement('div', { className: 'panel' },
          React.createElement('div', { className: 'panel-header' },
            React.createElement('span', { className: 'panel-title' }, 'Revision packages'),
            React.createElement('button', {
              className: 'btn btn-ghost btn-sm',
              onClick: () => navigate('sheets')
            },
              React.createElement(window.Icon, { name: 'layers', size: 12 }),
              'All drawings'
            )
          ),
          React.createElement('div', { className: 'data-table-wrap', style: { border: 'none', borderRadius: 0 } },
            React.createElement('table', { className: 'data-table' },
              React.createElement('thead', null,
                React.createElement('tr', null,
                  React.createElement('th', null, 'Package'),
                  React.createElement('th', null, 'Date'),
                  React.createElement('th', null, 'Disciplines'),
                  React.createElement('th', { className: 'col-right' }, 'Sheets'),
                  React.createElement('th', { className: 'col-right' }, 'Changes'),
                  React.createElement('th', null, 'Status'),
                  React.createElement('th', null, '')
                )
              ),
              React.createElement('tbody', null,
                revisionPackages.map(pkg =>
                  React.createElement('tr', { key: pkg.id },
                    React.createElement('td', { className: 'cell-mono' },
                      React.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: 8 } },
                        pkg.status === 'active' && React.createElement('div', { className: 'nav-pkg-dot' }),
                        pkg.label
                      )
                    ),
                    React.createElement('td', { className: 'cell-secondary' }, pkg.date),
                    React.createElement('td', { className: 'cell-secondary' }, pkg.discipline),
                    React.createElement('td', { className: 'col-right cell-mono' }, pkg.sheets),
                    React.createElement('td', { className: 'col-right cell-mono' }, pkg.changes),
                    React.createElement('td', null,
                      React.createElement(window.Badge, { status: pkg.status })
                    ),
                    React.createElement('td', { className: 'col-right' },
                      pkg.status === 'active'
                        ? React.createElement('button', {
                            className: 'btn btn-secondary btn-sm',
                            onClick: () => navigate('changes')
                          }, 'Review queue →')
                        : React.createElement('button', {
                            className: 'btn btn-ghost btn-sm',
                            onClick: () => navigate('export')
                          }, 'Export history')
                    )
                  )
                )
              )
            )
          )
        ),

        // Export readiness
        React.createElement('div', { className: 'panel' },
          React.createElement('div', { className: 'panel-header' },
            React.createElement('span', { className: 'panel-title' }, 'Export readiness'),
            React.createElement('button', {
              className: `btn btn-sm ${stats.pending === 0 ? 'btn-primary' : 'btn-secondary'}`,
              onClick: () => navigate('export')
            },
              React.createElement(window.Icon, { name: 'download', size: 12 }),
              stats.pending === 0 ? 'Generate workbook' : 'Export page'
            )
          ),
          React.createElement('div', { className: 'panel-body' },
            React.createElement('div', { className: 'export-status-bar', style: { border: 'none', padding: 0, background: 'transparent' } },
              React.createElement('div', { className: 'export-readiness', style: { flex: 1 } },
                React.createElement('div', { className: 'export-readiness-label' }, 'Review completion'),
                React.createElement('div', { className: 'progress-bar-track', style: { marginTop: 6 } },
                  React.createElement('div', {
                    className: `progress-bar-fill${pctComplete === 100 ? ' complete' : ''}`,
                    style: { width: pctComplete + '%' }
                  })
                ),
                React.createElement('div', { className: 'progress-label', style: { marginTop: 4 } },
                  stats.pending > 0
                    ? `${stats.pending} changes still pending — workbook will export with current decisions`
                    : 'All changes reviewed — ready to generate workbook'
                )
              )
            )
          )
        )
      )
    )
  );
}

Object.assign(window, { Overview });
