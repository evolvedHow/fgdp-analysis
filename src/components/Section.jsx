import React from 'react';

/**
 * One panel of the continuous data story.
 * Each section is a self-contained card that reads the same global filters.
 */
export default function Section({ id, step, kicker, title, lede, children, footer, aside }) {
  return (
    <section className="story-card" id={id} aria-labelledby={`${id}-title`}>
      <div className="story-head">
        <span className="step">{step}</span>
        <div>
          <p className="kicker">{kicker}</p>
          <h2 id={`${id}-title`}>{title}</h2>
          {lede && <p className="lede">{lede}</p>}
        </div>
      </div>
      <div className={`story-body ${aside ? 'with-aside' : ''}`}>
        <div className="story-main">{children}</div>
        {aside && <aside className="story-aside">{aside}</aside>}
      </div>
      {footer && <p className="story-footer">{footer}</p>}
    </section>
  );
}
