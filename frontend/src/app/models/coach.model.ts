export interface CoachMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface CoachConversation {
  id: number;
  messages: CoachMessage[];
  updated_at: string | null;
}

export interface CoachReply {
  reply: string;
}
