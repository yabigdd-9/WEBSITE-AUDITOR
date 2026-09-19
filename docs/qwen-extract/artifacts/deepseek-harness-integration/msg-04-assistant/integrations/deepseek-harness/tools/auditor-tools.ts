/**
 * AUDITOR TOOLS BRIDGE
 * Purpose: Expose safe, validated interfaces to ./mm CLI
 * Security: Input sanitization, strict timeouts, no raw shell passthrough
 */

import { execFile } from 'child_process';
import { promisify } from 'util';
import { z } from 'zod';

const execFileAsync = promisify(execFile);

// --- Schemas for Input Validation ---
const StatusInputSchema = z.object({
  action: z.enum(['runtime', 'polish']),
});

const AuditResultSchema = z.object({
  success: z.boolean(),
  data: z.any().optional(),
  error: z.string().optional(),
});

// --- Helper: Secure Executor ---
async function secureExec(command: string, args: string[], timeoutMs: number = 5000): Promise<string> {
  try {
    const { stdout } = await execFileAsync(command, args, {
      timeout: timeoutMs,
      env: { ...process.env, PYTHONUNBUFFERED: '1' }, // Ensure clean output
      cwd: '/app/workspace', // Force execution in isolated dir
    });
    return stdout.trim();
  } catch (error: any) {
    throw new Error(`EXEC_FAILURE: ${error.message}`);
  }
}

// --- Tool Definitions ---

export async function getAuditorStatus(input: unknown): Promise<z.infer<typeof AuditResultSchema>> {
  const parsed = StatusInputSchema.safeParse(input);
  if (!parsed.success) {
    return { success: false, error: 'INVALID_INPUT_SCHEMA' };
  }

  try {
    let cmdArgs: string[];
    if (parsed.data.action === 'runtime') {
      cmdArgs = ['--runtime'];
    } else if (parsed.data.action === 'polish') {
      cmdArgs = ['polish-status'];
    } else {
      return { success: false, error: 'UNSUPPORTED_ACTION' };
    }

    // Call the deterministic MM CLI
    const result = await secureExec('./mm', cmdArgs);
    
    // Attempt to parse JSON if expected, otherwise return raw text wrapped
    let data: any;
    try {
      data = JSON.parse(result);
    } catch {
      data = { raw_output: result };
    }

    return { success: true, data };
  } catch (err: any) {
    return { success: false, error: err.message };
  }
}

// Register with Harness SDK (Pseudo-code depending on specific Harness API)
// harness.registerTool('auditor_status', getAuditorStatus);
