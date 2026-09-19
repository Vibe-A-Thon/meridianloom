export type IconName =
  | 'overview'
  | 'delivery'
  | 'agents'
  | 'learning'
  | 'evidence'
  | 'runtime'
  | 'guide'
  | 'settings'
  | 'search'
  | 'plus'
  | 'arrow'
  | 'bell'
  | 'chevron'
  | 'check'
  | 'close'
  | 'focus'
  | 'menu'
  | 'play'
  | 'stop'
  | 'external'
  | 'spark'
  | 'layers'
  | 'skills'
  | 'instructions'
  | 'phases'
  | 'governance'
  | 'connectors';
const paths: Record<IconName, string> = {
  overview: 'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z',
  delivery: 'M4 4h16v16H4z M4 9h16 M9 9v11 M15 9v11',
  agents:
    'M8 10a4 4 0 1 0 0-8 4 4 0 0 0 0 8 M1 21v-3a7 7 0 0 1 14 0v3 M16 3a4 4 0 0 1 0 8 M18 14a6 6 0 0 1 5 6',
  learning: 'M2 8l10-5 10 5-10 5z M6 10v7c4 4 8 4 12 0v-7 M22 8v8',
  evidence: 'M5 3h11l3 3v15H5z M15 3v5h4 M8 12h8 M8 16h5',
  runtime: 'M2 12h4l3-8 6 16 3-8h4',
  guide: 'M12 5c-3-2-7-2-10-1v16c3-1 7-1 10 1 3-2 7-2 10-1V4c-3-1-7-1-10 1v16',
  settings: 'M4 6h16 M4 12h16 M4 18h16 M8 3v6 M16 9v6 M10 15v6',
  search: 'M10.5 3a7.5 7.5 0 1 0 0 15 7.5 7.5 0 0 0 0-15 M16 16l5 5',
  plus: 'M12 5v14 M5 12h14',
  arrow: 'M4 12h16 M14 6l6 6-6 6',
  bell: 'M18 8a6 6 0 0 0-12 0c0 8-3 8-3 9h18c0-1-3-1-3-9 M10 21h4',
  chevron: 'M9 5l7 7-7 7',
  check: 'M5 12l4 4L19 6',
  close: 'M6 6l12 12 M6 18 18 6',
  focus: 'M3 9V3h6 M15 3h6v6 M21 15v6h-6 M9 21H3v-6',
  menu: 'M3 6h18 M3 12h18 M3 18h18',
  play: 'M7 3l14 9-14 9z',
  stop: 'M5 5h14v14H5z',
  external: 'M14 3h7v7 M21 3 10 14 M10 3H3v18h18v-7',
  spark: 'M12 2l3 7 7 3-7 3-3 7-3-7-7-3 7-3z',
  layers: 'M2 7l10-5 10 5-10 5z M2 12l10 5 10-5 M2 17l10 5 10-5',
  // A loom shuttle: a skill is what a role agent is threaded with.
  skills: 'M3 12h18 M6 9l-3 3 3 3 M18 9l3 3-3 3 M9 5l6 14',
  // A page with a turned corner and rules: instruction files.
  instructions: 'M6 3h9l3 3v15H6z M15 3v4h3 M9 11h7 M9 15h7 M9 19h4',
  // Nine phases as a segmented track with a gate marker.
  phases: 'M3 12h4 M9 12h4 M15 12h6 M7 9v6 M13 9v6 M19 8v8',
  // A shield over a check: the gate that governs.
  governance: 'M12 3l8 3v6c0 5-4 8-8 9-4-1-8-4-8-9V6z M9 12l2 2 4-4',
  // Two halves of a coupling meeting in the middle: an external system joined.
  connectors:
    'M9 7H6a5 5 0 0 0 0 10h3 M15 7h3a5 5 0 0 1 0 10h-3 M8 12h8',
};
export function Icon({
  name,
  size = 18,
  className,
}: {
  name: IconName;
  size?: number;
  className?: string;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={className}
    >
      <path d={paths[name]} />
    </svg>
  );
}
