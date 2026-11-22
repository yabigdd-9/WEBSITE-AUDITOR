// .claude/workflows/orchestrator.js
/**
 * Task orchestrator that splits large tasks into parallel sub-tasks.
 * Uses Sonnet for complex tasks, Haiku for simple sub-tasks.
 * Checks remaining token budget per task.
 */

// Mock token budget tracker - in practice, this would interface with Claude Code's token tracking
let tokenBudget = {
  total: 100000, // example total tokens per session
  used: 0,
  get remaining() {
    return this.total - this.used;
  }
};

/**
 * Update token usage (would be called by actual tool invocations)
 * @param {number} tokens - tokens consumed
 */
function useTokens(tokens) {
  tokenBudget.used += tokens;
}

/**
 * Estimate tokens for a task description (simple heuristic)
 * @param {string} description - task description
 * @returns {number} estimated tokens
 */
function estimateTokens(description) {
  // Rough estimate: 4 chars per token
  return Math.ceil(description.length / 4);
}

/**
 * Determine if a task is complex based on token estimate and keywords
 * @param {string} description - task description
 * @param {number} estimatedTokens - estimated token count
 * @returns {boolean} true if complex
 */
function isComplexTask(description, estimatedTokens) {
  const complexKeywords = ['analyze', 'implement', 'refactor', 'design', 'architect', 'optimize'];
  const hasComplexKeyword = complexKeywords.some(keyword =>
    description.toLowerCase().includes(keyword)
  );
  return estimatedTokens > 1500 || hasComplexKeyword;
}

/**
 * Split a task description into sub-tasks (simple implementation)
 * @param {string} description - original task description
 * @returns {Array<string>} sub-task descriptions
 */
function splitIntoSubTasks(description) {
  // If description contains bullet points or numbered list, split by lines
  if (/[\n\r]/.test(description)) {
    const lines = description.split(/[\r\n]+/).filter(line => line.trim() !== '');
    if (lines.length > 1) return lines;
  }

  // If description contains semicolons or conjunctions, split
  if (/[;:]/.test(description)) {
    return description.split(/[;:]/).map(part => part.trim()).filter(part => part);
  }

  // Fallback: return as single sub-task
  return [description];
}

/**
 * Execute a sub-task with appropriate model
 * @param {string} subTaskDescription - description of sub-task
 * @param {string} model - 'sonnet' or 'haiku'
 * @returns {Promise<string>} result of sub-task execution
 */
async function executeSubTask(subTaskDescription, model) {
  // In a real implementation, this would invoke the appropriate Claude model
  // For demonstration, we simulate with a timeout and token usage tracking

  const estimatedTokens = estimateTokens(subTaskDescription);

  // Check token budget before execution
  if (tokenBudget.remaining < estimatedTokens) {
    throw new Error(`Insufficient token budget: ${tokenBudget.remaining} remaining, need ${estimatedTokens}`);
  }

  // Simulate model execution (replace with actual Claude invocation)
  return new Promise((resolve) => {
    setTimeout(() => {
      // Simulate some token usage (actual would be measured)
      const tokensUsed = Math.min(estimatedTokens, Math.max(100, estimatedTokens * 0.8));
      useTokens(tokensUsed);

      const result = `[${model.toUpperCase()}] Result for: "${subTaskDescription.substring(0, 50)}${subTaskDescription.length > 50 ? '...' : ''}"`;
      resolve(result);
    }, Math.random() * 100); // simulate variable execution time
  });
}

/**
 * Main orchestration function
 * @param {string} taskDescription - description of the task to orchestrate
 * @returns {Promise<Array>} results of all sub-tasks
 */
async function orchestrateTask(taskDescription) {
  console.log(`Orchestrating task: "${taskDescription.substring(0, 100)}${taskDescription.length > 100 ? '...' : ''}"`);

  const estimatedTokens = estimateTokens(taskDescription);

  // Check overall token budget
  if (tokenBudget.remaining < estimatedTokens) {
    throw new Error(`Insufficient token budget for task: ${tokenBudget.remaining} remaining, need ${estimatedTokens}`);
  }

  // Determine if task is complex
  const isComplex = isComplexTask(taskDescription, estimatedTokens);
  const model = isComplex ? 'sonnet' : 'haiku';

  console.log(`Task complexity: ${isComplex ? 'complex' : 'simple'} -> using ${model}`);

  // Split task into sub-tasks
  const subTaskDescriptions = splitIntoSubTasks(taskDescription);
  console.log(`Split into ${subTaskDescriptions.length} sub-tasks`);

  // Execute sub-tasks in parallel
  const subTaskPromises = subTaskDescriptions.map(subTaskDesc =>
    executeSubTask(subTaskDesc, model)
  );

  try {
    const results = await Promise.all(subTaskPromises);
    console.log(`Orchestration completed. Token budget remaining: ${tokenBudget.remaining}`);
    return results;
  } catch (error) {
    console.error(`Orchestration failed: ${error.message}`);
    throw error;
  }
}

module.exports = {
  orchestrateTask,
  // For testing/debugging
  getTokenBudget: () => ({ ...tokenBudget }),
  estimateTokens,
  isComplexTask,
  splitIntoSubTasks
};