import { useState } from 'react';
import { Icon } from './Icon';
import s from './workbench.module.css';
import form from './studio.module.css';

import { SURFACE_COVERAGE } from './surfaces';
export { SURFACE_COVERAGE } from './surfaces';

export function GuideStudio({ onNavigate }: { onNavigate: (route: string) => void }) {
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState('all');
  const shown = SURFACE_COVERAGE.filter(
    ([id, label, route, detail]) =>
      `${id} ${label} ${detail}`.toLowerCase().includes(query.toLowerCase()) &&
      (filter === 'all' || (filter === 'connected' ? route !== null : route === null)),
  );
  return (
    <div className={s.page}>
      <header className={s.pageHeading}>
        <div>
          <p className={s.eyebrow}>SYSTEM / WORKSPACE GUIDE</p>
          <h1>Find the thread you need.</h1>
          <p>
            Every specified surface has a place here, with its current implementation scope stated
            explicitly.
          </p>
        </div>
      </header>
      <div className={s.warning}>
        This workbench extends the existing recorder. Connected views may cover part of a larger
        specification; pending capabilities do not execute or display fabricated results.
      </div>
      <div className={form.toolbar}>
        <label className={form.search}>
          <Icon name="search" size={15} />
          <input
            aria-label="Search capability coverage"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Find a feature or specification…"
          />
        </label>
        <select
          className={s.select}
          aria-label="Coverage filter"
          value={filter}
          onChange={(event) => setFilter(event.target.value)}
        >
          <option value="all">All 51 surfaces</option>
          <option value="connected">Connected entry points</option>
          <option value="pending">Pending interfaces</option>
        </select>
      </div>
      <section className={s.panel} aria-label="Specification coverage">
        {shown.map(([id, label, route, detail]) => (
          <div className={s.checkRow} key={id}>
            <span className={s.statusBadge}>10.{id}</span>
            <div>
              <strong>{label}</strong>
              <p>{detail}</p>
            </div>
            {route ? (
              <button className={s.textButton} onClick={() => onNavigate(route)}>
                Explore <Icon name="arrow" size={14} />
              </button>
            ) : (
              <span className={s.statusBadge}>Pending</span>
            )}
          </div>
        ))}
        {shown.length === 0 && (
          <div className={s.empty}>
            <p>No surfaces match this search.</p>
          </div>
        )}
      </section>
    </div>
  );
}
