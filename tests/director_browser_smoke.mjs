// Drive both handoffs through the installed host and the real upstream viewport.
import { setTimeout as sleep } from "node:timers/promises";

const [port, mode] = process.argv.slice(2);
const deadline = Date.now() + 28_000;
let page;
while (!page && Date.now() < deadline) {
  try {
    const result = await fetch(`http://127.0.0.1:${port}/json/list`, { signal: AbortSignal.timeout(800) });
    page = (await result.json()).find(target =>
      target.type === "page" && /\/director_host\//.test(target.url) && target.webSocketDebuggerUrl
    );
  } catch {
    // The native window may still be starting.
  }
  if (!page) await sleep(200);
}
if (!page) throw new Error("The director host did not appear in the local WebView.");

const origin = new URL(page.url).origin;
const socket = new WebSocket(page.webSocketDebuggerUrl);
const requests = new Map();
const external = new Set();
let serial = 0;

function checkResource(url) {
  const target = new URL(url);
  if (["http:", "https:"].includes(target.protocol) && target.origin !== origin) external.add(target.origin);
}

socket.addEventListener("message", event => {
  const message = JSON.parse(event.data);
  if (message.method === "Network.requestWillBeSent") checkResource(message.params.request.url);
  const request = requests.get(message.id);
  if (!request) return;
  requests.delete(message.id);
  if (message.error) request.reject(new Error(message.error.message));
  else request.resolve(message.result);
});

function command(method, params = {}) {
  const id = ++serial;
  return new Promise((resolve, reject) => {
    requests.set(id, { resolve, reject });
    socket.send(JSON.stringify({ id, method, params }));
  });
}

async function evaluate(expression) {
  const response = await command("Runtime.evaluate", { expression, returnByValue: true });
  if (response.exceptionDetails) throw new Error(response.exceptionDetails.exception?.description);
  return response.result.value;
}

async function until(expression, message) {
  while (Date.now() < deadline) {
    if (await evaluate(expression)) return;
    await sleep(125);
  }
  const status = await evaluate('document.querySelector("#status")?.textContent');
  throw new Error(`${message} (${status ?? "no host status"})`);
}

function inDesk(expression) {
  return `(() => { const desk = document.querySelector('#desk')?.contentDocument; return desk && (${expression}); })()`;
}

async function clickDesk(selector) {
  const target = `desk.querySelector(${JSON.stringify(selector)})`;
  await until(inDesk(`Boolean(${target})`), `Missing director control ${selector}`);
  await evaluate(inDesk(`${target}.click()`));
}

try {
  await new Promise((resolve, reject) => {
    socket.addEventListener("open", resolve, { once: true });
    socket.addEventListener("error", () => reject(new Error("Could not attach to the local WebView.")), { once: true });
  });
  await command("Network.enable");
  await until('document.querySelector("#send") && !document.querySelector("#send").disabled', "Director bridge did not become ready");
  await until(inDesk('Boolean(desk.querySelector("canvas"))'), "The original 3D viewport did not load");
  if (mode === "pose") {
    await clickDesk('[aria-label="选择画幅比例"]');
    await clickDesk('.viewport-aspect-option:has(.viewport-aspect-option-frame-16-9)');
  } else {
    await clickDesk('[role="treeitem"][aria-label="角色01"] .object-select-button');
    await clickDesk('[aria-label="角色面板标签"] button:last-child');
    await clickDesk(".character-route-add");
    await clickDesk(".character-route-add");
    await until(inDesk('Boolean(desk.querySelector(\'[aria-label="选择路线点 2"]\'))'), "The second route point was not recorded");
  }
  const startupResources = await evaluate(`[...performance.getEntriesByType('resource'),
    ...document.querySelector('#desk').contentWindow.performance.getEntriesByType('resource')].map(entry => entry.name)`);
  startupResources.forEach(checkResource);
  if (external.size) throw new Error(`The director desk requested external origins: ${[...external].join(", ")}`);
  // The successful POST immediately closes this native window, so schedule the
  // UI click after Runtime.evaluate responds and let the caller verify the file.
  await evaluate('void setTimeout(() => document.querySelector("#send").click(), 75)');
  console.log(`Operated the bundled 3D director and requested ${mode} handoff.`);
} finally {
  socket.close();
}
