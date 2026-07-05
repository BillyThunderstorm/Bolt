import { base44 } from "@base44/sdk";

export default async function main(args: { query: string }) {
  const results: Array<{ conversationId: string; conversationTitle: string; messageContent: string; messageId: string }> = [];
  
  // Get all conversations
  const conversations = await base44.entities.Conversation.list();
  
  for (const conv of conversations) {
    const messages = await base44.entities.Message.list({
      where: { conversationId: conv.id },
    });
    
    for (const msg of messages) {
      if (msg.content.toLowerCase().includes(args.query.toLowerCase())) {
        results.push({
          conversationId: conv.id,
          conversationTitle: conv.title || "Untitled",
          messageContent: msg.content,
          messageId: msg.id,
        });
      }
    }
  }
  
  return results;
}
