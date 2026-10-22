import { spawn } from 'node:child_process';
const child = spawn(process.execPath, ['node_modules/next/dist/bin/next', 'dev', '--port', '3107'], {
  stdio: 'inherit', env: { ...process.env, NEXT_DIST_DIR: '.next-e2e', BACKEND_URL: 'http://127.0.0.1:8107' },
});
process.on('SIGTERM', () => child.kill());
process.on('SIGINT', () => child.kill());
child.on('exit', code => process.exit(code ?? 0));
