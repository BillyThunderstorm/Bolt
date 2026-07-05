import { base44 } from "@base44/sdk";

export default async function main(args: { category: string; content: string; importance?: "low" | "medium" | "high" }) {
  const memory = await base44.entities.Memory.create({
    data: {
      category: args.category,
      content: args.content,
      importance: args.importance || "medium",
    },
  });
  return { success: true, memory };
}
