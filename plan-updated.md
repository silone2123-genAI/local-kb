### 1. Requirements \& Planning (Discovery)

- Risk Assessment (Pre-mortem): Run structured pre-mortems using prompts across code, JIRA, and wiki artifacts to surface likely failure points.
- Clarification \& Gap Analysis: Identify ambiguities, missing edge cases, and conflicting requirements early.
  
***

### 2. Design \& Implementation (Build)

- Impact Analysis:
    - Analyze git branches and dependency trees to understand affected components.
    - Map code changes to JIRA scope and wiki specifications.
    - Use cutting edge thinking methodology to generate test scenarios from expected behavior changes.
- AI-Assisted Code Review: Use AI (Claude) for PR reviews (logic validation, edge cases, style).

***

### 3. Testing \& Quality Assurance (Verify)

- Test Generation:
    - Auto-generate unit and integration tests using Claude Code.
    - Use tools like Meteor Recorder + AI to convert user flows into structured test cases.
    - Use AI exchange simulator for automated testing
- Performance \& Reliability: Build View Server performance testing and monitor latency, throughput, and failure modes.
- Dependency Tracking: Monitor upstream/downstream component changes and release compatibility.
- Knowledge Gap Reduction: Identify unclear system behavior and improve documentation/test coverage.
- Bug Reporting \& Repro:
    - Capture video + structured logs for complex issues.
    - Auto-generate reproducible JIRA tickets with steps, expected vs actual behavior.

***

### 4. Deployment \& Post-Deployment (Release \& Operate)

- Utilize AI to write Deployment Notes: Generate deployment notes, change logs, and operational runbooks.

***

### 5. Supporting Tools

- Requirements Consolidation: Aggregate inputs from PRDs, support tickets (email/Slack/JIRA), and wiki docs into a unified requirement set/llm wiki - to assist dev support
- Use log replay to reconstruct real user scenarios in QA and Prod.

***
