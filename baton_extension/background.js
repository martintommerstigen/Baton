"use strict";

// This service worker never reads ChatGPT cookies or the browser's profile.
// It forwards only a user's chosen chat and its exact assistant tool frame to
// Baton's locally registered Native Messaging host. No HTTP/GitHub relay.
const HOST = "com.baton.greg";
const sessions = new Map();
const CHAT_PATH = /^\/c\/([0-9a-f]{8}-[0-9a-f-]{20,64})$/i;

function chatOf(url) {
  try {
    const u = new URL(url);
    if (u.protocol !== "https:" || u.origin !== "https://chatgpt.com" ||
        u.search || u.hash) return null;
    const m = CHAT_PATH.exec(u.pathname);
    return m ? m[1] : null;
  } catch (_) {
    return null;
  }
}

function tellTab(tabId, reply) {
  chrome.tabs.sendMessage(tabId, {type:"baton-native", reply}, () => {
    // A closed tab or changed chat may be unreachable; never retry execution.
    void chrome.runtime.lastError;
  });
}

function stopPort(tabId, reason) {
  const session = sessions.get(tabId);
  if (!session) return;
  sessions.delete(tabId);
  try { session.port.postMessage({op:"stop"}); } catch (_) {}
  try { session.port.disconnect(); } catch (_) {}
  tellTab(tabId, {ok:false,error:reason || "bridge-closed"});
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  const tabId = sender.tab && sender.tab.id;
  const current = chatOf(sender.tab && sender.tab.url);
  if (!Number.isInteger(tabId) || !current ||
      !message || typeof message !== "object") {
    sendResponse({queued:false,error:"not-existing-chatgpt-tab"});
    return false;
  }
  if (message.op === "arm") {
    if (current !== message.chat_id) {
      sendResponse({queued:false,error:"chat-id-mismatch"});
      return false;
    }
    stopPort(tabId, "replaced-session");
    try {
      const port = chrome.runtime.connectNative(HOST);
      const session = {port, chat_id:current};
      sessions.set(tabId, session);
      port.onMessage.addListener(reply => {
        if (sessions.get(tabId) !== session) return;
        if (reply && reply.op === "armed" && reply.chat_id !== current) {
          stopPort(tabId, "native-chat-id-mismatch");
          return;
        }
        tellTab(tabId, reply);
      });
      port.onDisconnect.addListener(() => {
        if (sessions.get(tabId) !== session) return;
        sessions.delete(tabId);
        tellTab(tabId, {ok:false,error:"native-host-disconnected"});
      });
      port.postMessage({op:"arm",chat_id:current});
      sendResponse({queued:true});
    } catch (_) {
      sessions.delete(tabId);
      sendResponse({queued:false,error:"native-host-unavailable"});
    }
    return false;
  }
  if (message.op === "stop") {
    stopPort(tabId, "stopped-by-user");
    sendResponse({queued:true});
    return false;
  }
  if (message.op === "execute_frame") {
    const session = sessions.get(tabId);
    if (!session || session.chat_id !== current ||
        message.chat_id !== current ||
        typeof message.frame !== "string" || message.frame.length > 7000 ||
        !message.frame.startsWith("BATON_TOOL_V2 ")) {
      sendResponse({queued:false,error:"not-authorized-for-chat"});
      return false;
    }
    try {
      session.port.postMessage({
        op:"execute_frame",chat_id:current,frame:message.frame
      });
      sendResponse({queued:true});
    } catch (_) {
      stopPort(tabId, "native-host-disconnected");
      sendResponse({queued:false,error:"native-host-disconnected"});
    }
    return false;
  }
  sendResponse({queued:false,error:"unsupported-operation"});
  return false;
});

chrome.tabs.onUpdated.addListener((tabId, changes) => {
  if (!changes.url) return;
  const current = chatOf(changes.url);
  if (sessions.has(tabId) && sessions.get(tabId).chat_id !== current) {
    stopPort(tabId,"chat-navigation-revoked");
  }
});
chrome.tabs.onRemoved.addListener(tabId => stopPort(tabId,"tab-closed"));
