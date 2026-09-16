export const CHAT_SESSION_STORAGE_KEY = 'warehouse_chat_session_id';

export const getOrCreateChatSessionId = (): string => {
  const existingSessionId = globalThis.sessionStorage.getItem(CHAT_SESSION_STORAGE_KEY);
  if (existingSessionId) {
    return existingSessionId;
  }

  return rotateChatSessionId();
};

export const rotateChatSessionId = (): string => {
  const sessionId = globalThis.crypto.randomUUID();
  globalThis.sessionStorage.setItem(CHAT_SESSION_STORAGE_KEY, sessionId);
  return sessionId;
};
