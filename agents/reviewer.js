/**
 * Review Agent for Website Auditor
 * Scans execution logs/JSONL artifacts to extract "Lessons Learned"
 * and suggests prompt improvements for next runs.
 */

const fs = require('fs');
const path = require('path');

class ReviewerAgent {
  constructor() {
    this.logsDir = path.join(__dirname, '..', '..', 'audits');
    this.improvementsDir = path.join(__dirname, '..', '..', '.claude', 'improvements');
    this.lessonsLearned = [];
    this.improvements = [];
  }

  /**
   * Scan execution logs and JSONL artifacts for lessons learned
   */
  async scanLogs() {
    try {
      // Check if logs directory exists
      if (!fs.existsSync(this.logsDir)) {
        console.log('No audits directory found');
        return [];
      }

      const files = fs.readdirSync(this.logsDir);
      const logFiles = files.filter(file =>
        file.endsWith('.jsonl') || file.endsWith('.log') || file.endsWith('.json')
      );

      for (const file of logFiles) {
        const filePath = path.join(this.logsDir, file);
        const content = fs.readFileSync(filePath, 'utf8');

        // Extract lessons learned from different log formats
        const lessons = this.extractLessonsFromContent(content, file);
        this.lessonsLearned.push(...lessons);
      }

      return this.lessonsLearned;
    } catch (error) {
      console.error('Error scanning logs:', error);
      return [];
    }
  }

  /**
   * Extract lessons learned from log content
   */
  extractLessonsFromContent(content, filename) {
    const lessons = [];
    const lines = content.split('\n');

    for (const line of lines) {
      // Look for common patterns indicating lessons learned
      const lessonPatterns = [
        /lesson\s*learned[:\s]+(.+)/i,
        /learned[:\s]+(.+)/i,
        /improvement[:\s]+(.+)/i,
        /better\s+way[:\s]+(.+)/i,
        // JSONL specific patterns
        /"lesson.*?":\s*"([^"]*)"/i,
        /"improvement.*?":\s*"([^"]*)"/i
      ];

      for (const pattern of lessonPatterns) {
        const match = line.match(pattern);
        if (match && match[1]) {
          lessons.push({
            lesson: match[1].trim(),
            source: filename,
            timestamp: new Date().toISOString()
          });
        }
      }

      // Also look for error patterns that could lead to improvements
      const errorPatterns = [
        /error[:\s]+(.+)/i,
        /failed[:\s]+(.+)/i,
        /exception[:\s]+(.+)/i
      ];

      for (const pattern of errorPatterns) {
        const match = line.match(pattern);
        if (match && match[1]) {
          lessons.push({
            lesson: `Avoid error: ${match[1].trim()}`,
            source: filename,
            timestamp: new Date().toISOString(),
            type: 'error_avoidance'
          });
        }
      }
    }

    return lessons;
  }

  /**
   * Generate prompt improvement suggestions based on lessons learned
   */
  generateImprovementSuggestions() {
    const suggestions = [];

    // Group similar lessons
    const groupedLessons = this.groupSimilarLessons(this.lessonsLearned);

    for (const [topic, lessons] of Object.entries(groupedLessons)) {
      if (lessons.length >= 2) { // Only suggest if we have multiple instances
        suggestions.push({
          topic: topic,
          suggestion: `Consider updating prompts to address recurring issue: ${topic}`,
          basedOn: lessons.length,
          examples: lessons.slice(0, 3).map(l => l.lesson),
          timestamp: new Date().toISOString()
        });
      }
    }

    // Add specific improvement suggestions based on common patterns
    suggestions.push(
      ...this.generateSpecificImprovements()
    );

    return suggestions;
  }

  /**
   * Group similar lessons by topic
   */
  groupSimilarLessons(lessons) {
    const groups = {};

    for (const lesson of lessons) {
      // Simple grouping by first few words or key phrases
      const key = lesson.lesson
        .toLowerCase()
        .split(' ')
        .slice(0, 3)
        .join(' ')
        .replace(/[^a-z0-9\s]/g, '');

      if (!groups[key]) {
        groups[key] = [];
      }
      groups[key].push(lesson);
    }

    return groups;
  }

  /**
   * Generate specific improvement suggestions based on observed patterns
   */
  generateSpecificImprovements() {
    const suggestions = [];

    // Check for common issues in website auditor logs
    const commonIssues = this.lessonsLearned.filter(lesson =>
      lesson.lesson.toLowerCase().includes('timeout') ||
      lesson.lesson.toLowerCase().includes('selector') ||
      lesson.lesson.toLowerCase().includes('element not found') ||
      lesson.lesson.toLowerCase().includes('network')
    );

    if (commonIssues.length > 0) {
      suggestions.push({
        topic: 'Selector and Timing Issues',
        suggestion: 'Add more robust element waiting and retry mechanisms in browser automation scripts',
        basedOn: commonIssues.length,
        examples: commonIssues.slice(0, 2).map(l => l.lesson),
        timestamp: new Date().toISOString()
      });
    }

    return suggestions;
  }

  /**
   * Save improvements to .claude/improvements/ directory
   */
  async saveImprovements() {
    try {
      // Create improvements directory if it doesn't exist
      if (!fs.existsSync(this.improvementsDir)) {
        fs.mkdirSync(this.improvementsDir, { recursive: true });
      }

      const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
      const improvementsFile = path.join(
        this.improvementsDir,
        `reviewer-suggestions-${timestamp}.json`
      );

      const improvementsData = {
        generatedAt: new Date().toISOString(),
        lessonsLearned: this.lessonsLearned,
        suggestions: this.generateImprovementSuggestions(),
        totalLogsScanned: this.lessonsLearned.length
      };

      fs.writeFileSync(
        improvementsFile,
        JSON.stringify(improvementsData, null, 2)
      );

      console.log(`Review improvements saved to: ${improvementsFile}`);
      return improvementsFile;
    } catch (error) {
      console.error('Error saving improvements:', error);
      return null;
    }
  }

  /**
   * Main execution function
   */
  async run() {
    console.log('Starting Reviewer Agent...');

    // Scan logs for lessons learned
    await this.scanLogs();
    console.log(`Found ${this.lessonsLearned.length} lessons learned`);

    // Generate and save improvements
    const improvementsFile = await this.saveImprovements();

    if (improvementsFile) {
      console.log('Reviewer Agent completed successfully');
      return true;
    } else {
      console.log('Reviewer Agent failed to save improvements');
      return false;
    }
  }
}

// Export for use in other modules
module.exports = ReviewerAgent;

// If run directly, execute the agent
if (require.main === module) {
  const agent = new ReviewerAgent();
  agent.run().then(success => {
    process.exit(success ? 0 : 1);
  }).catch(err => {
    console.error('Reviewer Agent crashed:', err);
    process.exit(1);
  });
}