const params = new URLSearchParams(location.search);
const token = params.get("token");
const instanceId = params.get("instanceId");
const language = params.get("language") === "en" ? "en" : "zh-CN";
const mode = params.get("mode");
const origin = location.origin;
const pose = mode === "pose";
const action = pose ? "export.frame" : "project.get";
const frame = document.querySelector("#desk");
const status = document.querySelector("#status");
const send = document.querySelector("#send");
const title = (zh, en) => language === "en" ? en : zh;
const pending = new Map();
let loading = true;
let ready = false;
let sending = false;

document.documentElement.lang = language;
frame.title = title("3D 导演台", "3D Director Desk");
document.title = `ComicFlow · ${frame.title}`;
document.querySelector("#name").textContent = document.title;
send.textContent = pose ? title("取当前画面作为参考", "Use current frame as reference")
  : title("把轨迹带入动作编排", "Send tracks to action sequence");
status.textContent = title("正在加载 3D 导演台…", "Loading the 3D Director Desk…");

// Keep the one-time bridge credential out of the location bar and iframe URL.
history.replaceState(null, "", location.pathname);

function requestDirector(actionName, options = {}) {
  const requestId = crypto.randomUUID();
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      pending.delete(requestId);
      reject(new Error(title("导演台响应超时，请重试。", "The Director Desk timed out. Try again.")));
    }, 30_000);
    pending.set(requestId, { actionName, resolve, reject, timer });
    frame.contentWindow.postMessage({
      type: "storyai:director-desk:request",
      payload: { requestId, action: actionName, options },
    }, origin);
  });
}

async function submit(result) {
  const response = await fetch("/__director_output", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-ComicFlow-Director": token },
    body: JSON.stringify(result),
    signal: AbortSignal.timeout(30_000),
  });
  const reply = await response.json();
  if (!response.ok || !reply.ok) {
    throw new Error(reply.error || title("ComicFlow 未能接收结果。", "ComicFlow could not receive the result."));
  }
}

async function sendResult(makeResult) {
  if (sending) return;
  sending = true;
  send.disabled = true;
  status.textContent = title("正在发送到 ComicFlow…", "Sending to ComicFlow…");
  try {
    await submit(await makeResult());
    status.textContent = title("已发送，正在返回 ComicFlow。", "Sent. Returning to ComicFlow.");
  } catch (error) {
    status.textContent = error.message;
    sending = false;
    send.disabled = !ready;
  }
}

async function connect() {
  if (!loading) return;
  loading = false;
  try {
    const capabilities = await requestDirector("capabilities.get");
    if (capabilities?.protocolVersion !== 1 || !capabilities.actions?.includes(action)) {
      throw new Error(title("导演台版本不支持这个操作。", "This version of Director Desk does not support this action."));
    }
    await submit({ kind: "ready" });
    ready = true;
    send.disabled = false;
    status.textContent = pose
      ? title("摆好人物和机位后，可把当前画面带入参考图预览。", "Set the pose and camera, then use the current frame in the reference preview.")
      : title("为人物或道具设置轨迹后，可带入当前项目。", "Create a character or prop route, then send it to the current project.");
  } catch (error) {
    status.textContent = error.message;
  }
}

function receive(event) {
  if (event.origin !== origin || event.source !== frame.contentWindow) return;
  const { type, payload } = event.data || {};
  if (type === "storyai:director-desk-ready") {
    void connect();
  } else if (type === "storyai:director-desk:response") {
    const entry = pending.get(payload?.requestId);
    if (!entry || payload.protocolVersion !== 1 || payload.action !== entry.actionName) return;
    pending.delete(payload.requestId);
    clearTimeout(entry.timer);
    if (payload.ok === true) {
      entry.resolve(payload.data);
    } else {
      entry.reject(new Error(payload.error?.message || title("导演台操作失败。", "The Director Desk operation failed.")));
    }
  } else if (type === "storyai:director-desk-close") {
    void sendResult(() => ({ kind: "close" }));
  } else if (type === "storyai:director-desk-captures-sent" && ready && pose && !sending) {
    const captures = payload?.captures;
    if (Array.isArray(captures) && captures.length === 1 && typeof captures[0]?.dataUrl === "string") {
      void sendResult(() => ({ kind: "pose", dataUrl: captures[0].dataUrl }));
    } else {
      status.textContent = title("请一次发送一张截图，或使用「取当前画面作为参考」。",
        "Send one capture at a time, or use the current frame as a reference.");
    }
  }
}

if (instanceId && token && ["pose", "action"].includes(mode)) {
  window.addEventListener("message", receive);
  send.addEventListener("click", () => {
    void sendResult(async () => {
      const result = await requestDirector(action, pose ? { position: "current", quality: "720p" } : {});
      return pose ? { kind: "pose", dataUrl: result.dataUrl } : { kind: "action", project: result.project };
    });
  });
  const url = new URL("../director_desk/", location.href);
  url.search = new URLSearchParams({ instanceId, hostOrigin: origin, theme: "dark" });
  frame.src = url.href;
  setTimeout(() => {
    if (loading) status.textContent = title("3D 导演台尚未就绪，请关闭窗口后重试。", "The 3D Director Desk is still starting. Close the window and try again.");
  }, 30_000);
} else {
  status.textContent = title("请从 ComicFlow 的角色动作设计或人物动作编排打开。", "Open from Character pose design or Action sequence in ComicFlow.");
}
