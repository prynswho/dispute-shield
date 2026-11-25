import React from 'react';

export function Empty({ title, children }) {
  return <div className="empty"><span className="empty-icon" aria-hidden="true">◇</span><h3>{title}</h3><p>{children}</p></div>;
}

export function Metric({ name, value, detail }) {
  return <div className="metric"><span>{name}</span><strong>{value}</strong>{detail && <small>{detail}</small>}</div>;
}

export function Badge({ children, kind = '' }) {
  return <span className={`badge ${kind}`}>{children}</span>;
}

export function RiskBadge({ tier }) {
  return <Badge kind={tier ?? ''}>{tier ?? 'Unscored'}</Badge>;
}

