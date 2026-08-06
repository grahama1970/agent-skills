import { createContext, useContext } from 'react'
import { CHAT_READABLE, chatTokensForDensity, type ChatDensity, type ChatReadableTokens } from './spartaChatNvis'

const ChatReadableContext = createContext<ChatReadableTokens>(CHAT_READABLE)

export function ChatReadableProvider({
  value,
  density,
  children,
}: {
  value?: ChatReadableTokens
  density?: ChatDensity
  children: React.ReactNode
}) {
  return <ChatReadableContext.Provider value={value ?? (density ? chatTokensForDensity(density) : CHAT_READABLE)}>{children}</ChatReadableContext.Provider>
}

export function useChatReadable(): ChatReadableTokens {
  return useContext(ChatReadableContext)
}
