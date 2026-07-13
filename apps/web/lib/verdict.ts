import type { TrafficLight } from './types';

// The single source of truth for how a claim's traffic light renders. This is the
// honest-negative guarantee in code: only a green claim is ever a pass, and only a green
// claim gets the success colour token and the check icon. Yellow, red, and any unknown
// value are never a pass and never use the success token or the check icon (AC-WEB-6).

export interface VerdictStyle {
  token: 'success' | 'warning' | 'danger';
  label: string;
  icon: 'check' | 'alert' | 'cross';
  isPass: boolean;
}

const GREEN: VerdictStyle = { token: 'success', label: 'Grounded', icon: 'check', isPass: true };
const YELLOW: VerdictStyle = { token: 'warning', label: 'Needs review', icon: 'alert', isPass: false };
const RED: VerdictStyle = { token: 'danger', label: 'Flagged', icon: 'cross', isPass: false };

export function verdictStyle(light: TrafficLight | null | undefined): VerdictStyle {
  if (light === 'green') return GREEN;
  if (light === 'red') return RED;
  return YELLOW; // yellow, null, or anything unknown resolves to a non-pass review state
}
