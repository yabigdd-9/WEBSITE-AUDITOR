import { execSync } from 'child_process';
import { z } from 'zod'; // For input validation

const AuditorStatusSchema = z.object({
  command: z.literal('status'),
});

export async function getAuditorStatus(input: unknown): Promise<string> {
  const parsed = AuditorStatusSchema.safeParse(input);
  if (!parsed.success) throw new Error("Invalid input");

  try {
    // Execute deterministic MM CLI
    const result = execSync('./mm --runtime', { 
      encoding: 'utf-8',
      timeout: 5000, // Prevent hanging
      stdio: ['pipe', 'pipe', 'ignore'] // Ignore stderr noise
    });
    
    return JSON.stringify({ success: true, data: result.trim() });
  } catch (error) {
    return JSON.stringify({ success: false, error: "MM_CLI_FAILURE" });
  }
}

// Register tool with DeepSeek Harness SDK here...
