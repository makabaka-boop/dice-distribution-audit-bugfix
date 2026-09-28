// Start a real Flask server and the Vite preview server for the browser test.
import { spawn } from 'node:child_process';
import { connect } from 'node:net';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..', '..');
const UI = path.join(ROOT, 'ui');

function waitForPort(port, timeoutMs = 45_000) {
  const deadline = Date.now() + timeoutMs;
  return new Promise((resolve, reject) => {
    const attempt = () => {
      const socket = connect(port, '127.0.0.1');
      socket.once('connect', () => {
        socket.end();
        resolve();
      });
      socket.once('error', () => {
        socket.destroy();
        if (Date.now() > deadline) reject(new Error(`port ${port} never opened`));
        else setTimeout(attempt, 250);
      });
    };
    attempt();
  });
}

async function globalSetup() {
  const python = process.env.PYTHON || 'python3';

  // Real HTTP odds service (Flask dev server is fine for the e2e run).
  const odds = spawn(python, ['app.py'], {
    cwd: path.join(ROOT, 'odds'),
    stdio: 'inherit'
  });

  // Vite preview serves the production-built dist/ directory and proxies
  // /api to port 5000 (see vite.config.js), mirroring the nginx setup.
  const ui = spawn(
    'npx',
    ['vite', 'preview', '--host', '127.0.0.1', '--port', '4173'],
    {
      cwd: UI,
      stdio: 'inherit',
      shell: process.platform === 'win32'
    }
  );

  await waitForPort(5000);
  await waitForPort(4173);

  return async () => {
    odds.kill('SIGTERM');
    ui.kill('SIGTERM');
  };
}

export default globalSetup;
