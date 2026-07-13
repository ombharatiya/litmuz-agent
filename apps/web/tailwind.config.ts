import type { Config } from 'tailwindcss';

// Deep Emerald on a white base. Brand accent (#00674F) is for structure and actions only;
// verdicts use the separate success/warning/danger tokens so the brand colour is never
// mistaken for a pass (AC-WEB-DS-1). Exactly two font families (AC-WEB-DS-2).
export default {
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}', './lib/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: 'hsl(var(--bg))',
        ink: 'hsl(var(--ink))',
        'ink-soft': 'hsl(var(--ink-soft))',
        'ink-mute': 'hsl(var(--ink-mute))',
        rule: 'hsl(var(--rule))',
        accent: 'hsl(var(--accent))',
        success: 'hsl(var(--success))',
        warning: 'hsl(var(--warning))',
        danger: 'hsl(var(--danger))',
      },
      fontFamily: {
        sans: ["'Inter Tight'", 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ["'JetBrains Mono'", 'ui-monospace', 'monospace'],
      },
      borderRadius: { none: '0px', DEFAULT: '2px', full: '9999px' },
    },
  },
  plugins: [],
} satisfies Config;
