import type { TrafficLight } from '@/lib/types';
import { verdictStyle } from '@/lib/verdict';

// Icon paths keyed by name. The check is reserved for a pass; alert and cross are the
// non-pass icons. The colour never carries meaning alone: an icon and a literal label
// always accompany it (AC-WEB-DS-3).
const ICON_PATH: Record<string, string> = {
  check: 'M5 13l4 4L19 7',
  alert: 'M12 9v4m0 3.5h.01',
  cross: 'M6 6l12 12M18 6L6 18',
};

export function VerdictBadge({ light }: { light: TrafficLight | null }) {
  const style = verdictStyle(light);
  return (
    <span
      className={`verdict-badge verdict-${style.token}`}
      data-token={style.token}
      data-icon={style.icon}
      data-light={light ?? 'pending'}
      role="status"
      aria-label={style.label}
    >
      <svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2">
        <path d={ICON_PATH[style.icon]} strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <span className="verdict-label">{style.label}</span>
    </span>
  );
}
