/* 5481 by default, and whatever the run was given where another run of this
   same fixture already holds that port (the browser script's --port). The port
   is never silently fallen back from: two fixtures on one port would answer
   each other's checks. */
const port = Number(process.env.MAGNET_MINI_FIXTURE_PORT ?? 5481)
export default { esbuild: { jsx: 'automatic' }, server: { host: '127.0.0.1', port, strictPort: true } }
