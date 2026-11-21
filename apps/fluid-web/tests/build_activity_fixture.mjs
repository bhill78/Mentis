import { build } from 'esbuild'
await build({ entryPoints: ['tests/activity_recorded_fixture.tsx'], bundle: true, outfile: 'dist-activity-fixture/fixture.js', format: 'esm', jsx: 'automatic', define: { 'import.meta.env': '{}' } })
