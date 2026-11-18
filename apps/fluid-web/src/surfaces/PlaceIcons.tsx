/* THE BRAIN-LEVEL PLACES, EACH BY ITS OWN GLYPH.
 *
 * Three places sit together wherever the interface offers them -- the Brain
 * itself, the Sources it has acquired, and the 3D Brain -- and the owner asked
 * for the 3D Brain to be visible beside the other two rather than a line of
 * text among them (2026-11-18, ent-46aecf919fe8: "A 3D icon should be near the
 * manage sources and knowledge for the 3d brain").
 *
 * They are drawn here once so the rail, the top line on a phone and the Brain
 * menu's rows cannot drift apart: the same shape means the same place
 * everywhere. The Brain and Sources glyphs are the ones the rail already drew,
 * lifted unchanged; the cube is the new one.
 *
 * Stroked with `currentColor` at the size asked for, and `aria-hidden`: each is
 * decoration beside a control that already has a name. */

const box = (size: number) => ({
  viewBox: '0 0 16 16',
  width: size,
  height: size,
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.3,
  'aria-hidden': true as const,
})

/** the Brain this page serves */
export const BrainGlyph = ({ size = 16 }: { size?: number }) => (
  <svg {...box(size)}>
    <path d="M6 2.5a2 2 0 0 0-2 2v.3A2.2 2.2 0 0 0 2.5 7a2.2 2.2 0 0 0 .7 1.6A2.3 2.3 0 0 0 5 12.4 1.8 1.8 0 0 0 8 13V3.6A1.9 1.9 0 0 0 6 2.5Z" />
    <path d="M10 2.5a2 2 0 0 1 2 2v.3A2.2 2.2 0 0 1 13.5 7a2.2 2.2 0 0 1-.7 1.6 2.3 2.3 0 0 1-1.8 3.8A1.8 1.8 0 0 1 8 13" />
  </svg>
)

/** material acquired into the Brain (Manage Sources) */
export const SourcesGlyph = ({ size = 16 }: { size?: number }) => (
  <svg {...box(size)}>
    <ellipse cx="8" cy="4" rx="5" ry="2" />
    <path d="M3 4v8c0 1.1 2.2 2 5 2s5-.9 5-2V4" />
    <path d="M3 8c0 1.1 2.2 2 5 2s5-.9 5-2" />
  </svg>
)

/** THE 3D BRAIN: a cube seen in space, with its three visible edges meeting at
 *  the near corner -- the one glyph in this set that is drawn with depth,
 *  because depth is what the place is. */
export const SpaceGlyph = ({ size = 16 }: { size?: number }) => (
  <svg {...box(size)} strokeLinejoin="round">
    <path d="M8 1.6 14 5v6l-6 3.4L2 11V5Z" />
    <path d="M2 5l6 3.4L14 5" />
    <path d="M8 8.4v6" />
  </svg>
)

/** Governance over the whole Brain (Manage Brain) */
export const GovernanceGlyph = ({ size = 16 }: { size?: number }) => (
  <svg {...box(size)} strokeLinejoin="round">
    <path d="M8 1.8l5 1.9v4c0 3-2.1 5.3-5 6.5-2.9-1.2-5-3.5-5-6.5v-4Z" />
    <path d="M5.8 8.1 7.4 9.7l3-3.3" />
  </svg>
)
