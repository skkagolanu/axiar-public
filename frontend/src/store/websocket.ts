import { create } from 'zustand';

interface WebSocketState {
  connected: boolean;
  messages: any[];
  setConnected: (connected: boolean) => void;
  addMessage: (message: any) => void;
  clearMessages: () => void;
}

export const useWebSocketStore = create<WebSocketState>((set) => ({
  connected: false,
  messages: [],
  setConnected: (connected) => set({ connected }),
  addMessage: (message) => set((state) => ({ messages: [...state.messages, message] })),
  clearMessages: () => set({ messages: [] }),
}));
