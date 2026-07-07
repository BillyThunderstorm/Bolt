import { base44 } from "@base44/sdk";

export default async function main(args: { category?: string; minImportance?: number }) {
  let query: Record<string, any> = {};
  
  if (args.category) query.category = args.category;
  if (args.minImportance) query.importance_gte = args.minImportance;
  
  return await base44.entities.Memory.list({ where: query });
}
