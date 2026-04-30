// Change Detail — the cockpit. Most important screen.
// Keyboard: A=accept+next, R=reject+next, S=save, [=prev, ]=next

function ChangeDetail({ changeId, navigate }) {
  const { changes } = window.SCOPEDATA;
  const idx = changes.findIndex(c => c.id === changeId);
  const change = changes[idx] || changes[0];
  const actualIdx = idx >= 0 ? idx : 0;

  const [status, setStatus] = React.useState(change.status);
  const [scope, setScope] = React.useState(change.scope);
  const [notes, setNotes] = React.useState('');
  const [flash, setFlash] = React.useState(null);
  const scopeRef = React.useRef(null);
  const notesRef = React.useRef(null);

  // Sync state when change switches
  React.useEffect(() => {
    setStatus(change.status);
    setScope(change.scope);
    setNotes('');
    setFlash(null);
  }, [change.id]);

  const showFlash = (msg, type = 'success') => {
    setFlash({ msg, type });
    setTimeout(() => setFlash(null), 2200);
  };

  const doAccept = () => {
    setStatus('accepted');
    showFlash('Accepted — moving to next');
    setTimeout(() => {
      if (actualIdx < changes.length - 1) navigate('change-detail', changes[actualIdx + 1].id);
      else navigate('changes');
    }, 600);
  };

  const doReject = () => {
    setStatus('rejected');
    showFlash('Rejected', 'warning');
    setTimeout(() => {
      if (actualIdx < changes.length - 1) navigate('change-detail', changes[actualIdx + 1].id);
      else navigate('changes');
    }, 600);
  };

  const doSave = () => {
    showFlash('Saved');
  };

  const goPrev = () => {
    if (actualIdx > 0) navigate('change-detail', changes[actualIdx - 1].id);
  };
  const goNext = () => {
    if (actualIdx < changes.length - 1) navigate('change-detail', changes[actualIdx + 1].id);
  };

  // Keyboard shortcuts
  React.useEffect(() => {
    const handler = (e) => {
      const tag = document.activeElement?.tagName;
      if (tag === 'TEXTAREA' || tag === 'INPUT') return;
      if (e.key === 'a' || e.key === 'A') { e.preventDefault(); doAccept(); }
      if (e.key === 'r' || e.key === 'R') { e.preventDefault(); doReject(); }
      if (e.key === 's' || e.key === 'S') { e.preventDefault(); doSave(); }
      if (e.key === '[') { e.preventDefault(); goPrev(); }
      if (e.key === ']') { e.preventDefault(); goNext(); }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [actualIdx, scope, notes]);

  const pendingChanges = changes.filter(c => c.status === 'pending');
  const pendingIdx = pendingChanges.findIndex(c => c.id === change.id);

  return React.createElement('div', {
    style: { display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }
  },
    // Header bar
    React.createElement('div', { className: 'cockpit-header' },
      React.createElement('button', { className: 'cockpit-back', onClick: () => navigate('changes') },
        React.createElement(window.Icon, { name: 'arrow-left', size: 14 }),
        'Review Changes'
      ),

      React.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: '16px' } },
        React.createElement('span', { className: 'cockpit-id' },
          React.createElement('span', { style: { fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' } },
            change.sheet
          ),
          React.createElement('span', { className: 'cloud-label' }, ` · Cloud ${change.cloud}`),
          React.createElement('span', { style: { color: 'var(--text-tertiary)', marginLeft: '8px', fontSize: 'var(--text-sm)' } },
            change.rev
          )
        ),
        React.createElement(window.Badge, { status }),
        change.needsCheck && React.createElement(window.Badge, { needsCheck: true })
      ),

      React.createElement('div', { className: 'cockpit-nav' },
        React.createElement('button', {
          className: 'cockpit-nav-btn',
          onClick: goPrev,
          disabled: actualIdx === 0,
          title: 'Previous change  [  ['
        }, React.createElement(window.Icon, { name: 'chevron-left', size: 14 })),

        React.createElement('span', { className: 'cockpit-nav-pos' },
          `${actualIdx + 1} / ${changes.length}`
        ),

        React.createElement('button', {
          className: 'cockpit-nav-btn',
          onClick: goNext,
          disabled: actualIdx === changes.length - 1,
          title: 'Next change  ]'
        }, React.createElement(window.Icon, { name: 'chevron-right', size: 14 })),

        React.createElement('div', { style: { width: '1px', height: '20px', background: 'var(--rule-hairline)', margin: '0 4px' } }),

        React.createElement('button', {
          className: 'btn btn-primary btn-sm',
          onClick: () => navigate('changes'),
          style: { gap: '6px' }
        },
          React.createElement(window.Icon, { name: 'skip-forward', size: 12 }),
          pendingChanges.length > 0 ? `${pendingChanges.length} pending` : 'Queue'
        )
      )
    ),

    // Flash message
    flash && React.createElement('div', {
      style: { padding: '0 24px', paddingTop: '10px', position: 'absolute', top: '48px', left: 'var(--nav-width)', right: 0, zIndex: 50 }
    },
      React.createElement('div', { className: `flash flash-${flash.type}` },
        React.createElement(window.Icon, { name: flash.type === 'success' ? 'check-circle' : 'alert-triangle', size: 14 }),
        flash.msg
      )
    ),

    // Main cockpit split
    React.createElement('div', { className: 'cockpit-layout', style: { flex: 1 } },

      // Left — image pane
      React.createElement('div', { className: 'cockpit-image-pane' },
        React.createElement('div', { className: 'cockpit-image-stage' },
          React.createElement('div', { style: { position: 'relative' } },
            React.createElement('div', { className: 'cockpit-image-label' },
              React.createElement('span', null, change.sheet),
              React.createElement('span', { style: { color: 'var(--rule-hairline)' } }, '·'),
              React.createElement('span', { className: 'cloud-id' }, `Cloud ${change.cloud}`)
            ),
            React.createElement('div', { className: 'cockpit-image-wrap' },
              React.createElement('img', {
                src: `https://placehold.co/760x520/0d0c0a/2a2820?text=${encodeURIComponent(change.sheet + ' · Cloud ' + change.cloud)}`,
                alt: `${change.sheet} cloud ${change.cloud} crop`,
                style: { display: 'block', maxHeight: '58vh', maxWidth: '100%' }
              })
            )
          )
        ),

        // Sheet context strip
        React.createElement('div', {
          style: {
            borderTop: '1px solid var(--rule-hairline)',
            padding: '10px 24px',
            display: 'flex',
            alignItems: 'center',
            gap: '24px',
            background: 'var(--surface-base)',
            flexShrink: 0,
            position: 'relative',
            zIndex: 1
          }
        },
          React.createElement('span', {
            style: { fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', letterSpacing: '0.06em', textTransform: 'uppercase' }
          }, 'Sheet context'),
          React.createElement('span', {
            style: { fontSize: 'var(--text-sm)', color: 'var(--text-secondary)' }
          }, change.title),
          React.createElement('span', {
            style: { fontSize: 'var(--text-xs)', fontFamily: 'var(--font-mono)', color: 'var(--text-tertiary)' }
          }, change.discipline),
          React.createElement('button', {
            className: 'btn btn-ghost btn-sm',
            style: { marginLeft: 'auto' },
            onClick: () => navigate('sheet-detail', 'sh003')
          },
            React.createElement(window.Icon, { name: 'external-link', size: 12 }),
            'Full sheet'
          )
        )
      ),

      // Right — form pane
      React.createElement('div', { className: 'cockpit-form-pane' },
        React.createElement('div', { className: 'cockpit-form-scroll' },

          // Metadata grid
          React.createElement('div', { className: 'cockpit-meta' },
            React.createElement('div', { className: 'meta-pair' },
              React.createElement('span', { className: 'meta-key' }, 'Sheet'),
              React.createElement('span', { className: 'meta-val mono' }, change.sheet)
            ),
            React.createElement('div', { className: 'meta-pair' },
              React.createElement('span', { className: 'meta-key' }, 'Cloud'),
              React.createElement('span', { className: 'meta-val mono' }, change.cloud)
            ),
            React.createElement('div', { className: 'meta-pair' },
              React.createElement('span', { className: 'meta-key' }, 'Revision'),
              React.createElement('span', { className: 'meta-val' }, change.rev)
            ),
            React.createElement('div', { className: 'meta-pair' },
              React.createElement('span', { className: 'meta-key' }, 'Discipline'),
              React.createElement('span', { className: 'meta-val' }, change.discipline)
            ),
            React.createElement('div', { className: 'meta-pair span-2' },
              React.createElement('span', { className: 'meta-key' }, 'Sheet title'),
              React.createElement('span', { className: 'meta-val' }, change.title)
            )
          ),

          React.createElement('div', { className: 'cockpit-divider' }),

          // Scope text
          React.createElement('div', null,
            React.createElement('div', { className: 'cockpit-scope-label' }, 'Scope of change'),
            React.createElement('textarea', {
              ref: scopeRef,
              className: 'scope-textarea',
              value: scope,
              onChange: e => setScope(e.target.value),
              rows: 5
            })
          ),

          // Notes
          React.createElement('div', null,
            React.createElement('div', { className: 'cockpit-scope-label' }, 'Reviewer notes'),
            React.createElement('textarea', {
              ref: notesRef,
              className: 'notes-textarea',
              value: notes,
              placeholder: 'Optional — field conditions, cross-references, RFI numbers…',
              onChange: e => setNotes(e.target.value),
              rows: 3
            })
          ),

          // Save notes button
          React.createElement('div', null,
            React.createElement('button', {
              className: 'btn btn-secondary btn-sm',
              onClick: doSave
            },
              React.createElement(window.Icon, { name: 'check', size: 12 }),
              'Save notes'
            )
          )
        ),

        // Accept / Reject
        React.createElement('div', { className: 'cockpit-actions' },
          React.createElement('button', {
            className: 'btn-accept-full',
            onClick: doAccept
          },
            React.createElement(window.Icon, { name: 'check', size: 16 }),
            'Accept + Next',
            React.createElement(window.Kbd, null, 'A')
          ),
          React.createElement('button', {
            className: 'btn-reject-full',
            onClick: doReject
          },
            React.createElement(window.Icon, { name: 'x', size: 16 }),
            'Reject + Next',
            React.createElement(window.Kbd, null, 'R')
          )
        )
      )
    ),

    // Footer keyboard hint bar
    React.createElement('div', { className: 'cockpit-footer' },
      React.createElement('span', { className: 'kbd-hint' },
        React.createElement(window.Kbd, null, 'A'), 'Accept + next'
      ),
      React.createElement('span', { className: 'kbd-hint' },
        React.createElement(window.Kbd, null, 'R'), 'Reject + next'
      ),
      React.createElement('span', { className: 'kbd-hint' },
        React.createElement(window.Kbd, null, 'S'), 'Save'
      ),
      React.createElement('span', { className: 'kbd-hint' },
        React.createElement(window.Kbd, null, '['),
        React.createElement(window.Kbd, null, ']'),
        'Navigate'
      ),
      React.createElement('span', { style: { flex: 1 } }),
      React.createElement('span', {
        style: { fontSize: 'var(--text-xs)', fontFamily: 'var(--font-mono)', color: 'var(--text-tertiary)' }
      }, pendingChanges.length > 0 ? `${pendingChanges.length} pending in queue` : 'Queue clear')
    )
  );
}

Object.assign(window, { ChangeDetail });
