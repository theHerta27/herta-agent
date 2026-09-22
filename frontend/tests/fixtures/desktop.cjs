// Test entry only. Inject an offline provider host without a production test switch.
const path = require('node:path');
const childProcess = require('node:child_process');
const originalSpawn = childProcess.spawn;
childProcess.spawn = function (file, args, options) {
  if (Array.isArray(args) && args[1]?.endsWith('backend_host.py')) {
    args = [...args];
    args[1] = path.join(__dirname, 'service.py');
  }
  return originalSpawn(file, args, options);
};
require('../../dist/electron/main.cjs');
