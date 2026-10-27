import { F3, type Example } from './model'

export const dungeonExamples: Example[] = [
  {
    id: 'dungeon-player',
    category: 'dungeon helper',
    title: 'Dungeon Helper — PLAYER scope (local model)',
    note:
      'A real conversation with qwen3.5:9b through the Mark IV local-model path. It only picks ids and the kind of interaction; Mentis retrieves (within player scope), draws and pins. Open "▸" under a reply to see exactly what the model was sent and wrote. "Ask without renderers (A)" asks the same model the same thing as plain text.',
    demands: ['Needs the helper backend running: python experiments/dungeon_helper/server.py (127.0.0.1:8794), and your Connect: nothing is contacted until you press it.'],
    source: `${F3}helper version=1 scope=player title="Player helper"
${F3}`,
  },
  {
    id: 'dungeon-dm',
    category: 'dungeon helper',
    title: 'Dungeon Helper — DM scope (same model, whole campaign)',
    note: 'Same model and instruction; the backend supplies DM-only material too. Ask both helpers "Who leads the Black Hand?" or "Who does Hesta secretly work for?".',
    source: `${F3}helper version=1 scope=dm title="DM helper"
${F3}`,
  },
  {
    id: 'dungeon-no-grant',
    category: 'dungeon helper',
    title: 'A campaign reference with no helper session',
    note: 'The same camp: reference outside any helper: nothing grants it, so nothing is fetched and nothing is guessed.',
    source: `${F3}ref version=1 id=camp:npc-hesta
${F3}`,
  },
]
