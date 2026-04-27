# Consolidation Plan Agent Specification

## 🎯 Skill Goal
To generate a highly concrete, practical, and parameterized consolidation plan for a release candidate of a desktop GUI application (e.g., an equity trading application). The plan must synthesize disparate inputs into a single, actionable, and risk-aware Markdown document.

## ⚙️ Skill Parameters (Required Inputs)
The agent must accept and utilize the following three primary inputs:

1. **Project Context (string/file):**
    *   *Description:* High-level documentation about the application, its current state, target users, and architectural constraints.
    *   *Examples:* Link to the main project README, a brief summary of the current application stack (e.g., JavaFX/Electron/Qt), and the overall business goals for the release.
2. **Specific Focus Areas (list/string):**
    *   *Description:* A list of prioritized features, bug fixes, or architectural improvements that must be included in the release.
    *   *Format:* A bulleted list of objectives (e.g., "Implement real-time WebSocket data feeds," "Refactor the charting module to use the new library," "Fix critical memory leak in the login screen").
3. **Release Artifacts (list/file):**
    *   *Description:* Specific, detailed deliverables for this release candidate.
    *   *Format:* A structured list of components, versions, and required QA sign-offs (e.g., "Module A v1.2.0 (Code Review Passed)," "API endpoint `/trade` deployed to staging," "GUI component library v3.0").

## 📄 Expected Output Format (Structured Markdown)
The final output must be a single Markdown document, strictly adhering to the following structure:

### # 🚀 Release Consolidation Plan: [Release Name/Version]

#### 🗓️ I. High-Level Timeline & Milestones
*   *Goal:* Provide a chronological, top-level view of the release lifecycle.
*   *Content:*
    *   **Phase 1: Feature Freeze & QA Start:** [Date/Duration]
    *   **Phase 2: Stabilization & Bug Fixing:** [Date/Duration]
    *   **Phase 3: Internal Review & Deployment:** [Date/Duration]
    *   **Go/No-Go Decision Point:** [Specific Date/Criteria]

#### ✅ II. Detailed Actionable Steps
*   *Goal:* Convert Focus Areas and Artifacts into a sequence of tasks.
*   *Structure:* A prioritized checklist, categorized by team or phase.

**A. Feature Implementation (From Focus Areas)**
*   **[Feature Name]**
    *   [Action Step 1: Detailed task for development]
    *   [Action Step 2: Required testing steps]
    *   *Status:* (TODO / In Progress / Complete)
*   *(Repeat for all Focus Areas)*

**B. Technical Debt / Refactoring**
*   **[Component]**
    *   [Action Step 1: Refactoring task]
    *   *Status:* (TODO / In Progress / Complete)

**C. Artifact Validation (From Release Artifacts)**
*   **[Artifact Name]**
    *   [Verification Step: How QA/Dev Ops will validate this artifact]
    *   *Sign-off Required:* (List of required roles/individuals)

#### 🚧 III. High-Risk Roadblocks & Contingencies
*   *Goal:* Proactively identify points of failure based on Project Context and Focus Areas.
*   *Structure:* A list of critical risks, their impact, and a proposed mitigation strategy.

**Risk 1: [Description of Risk - e.g., Dependency Conflict]**
*   *Impact:* (High/Medium/Low - e.g., Total feature blockage)
*   *Mitigation Strategy:* (Specific action to prevent or reduce the impact)
*   *Owner:* (Team/Individual responsible for monitoring)

**Risk 2: [Description of Risk - e.g., Performance Degradation]**
*   *Impact:* (e.g., Slow UI interaction on older hardware)
*   *Mitigation Strategy:* (e.g., Implement aggressive caching, profile code paths)
*   *Owner:* (Team/Individual responsible for monitoring)

## 🧠 Agent Instructions (Internal Logic)
1.  **Input Analysis:** First, parse the `Project Context` to understand the application's constraints and risk profile.
2.  **Task Deconstruction:** Deconstruct `Specific Focus Areas` into discrete, measurable tasks. Prioritize these tasks based on dependencies identified in the `Project Context`.
3.  **Verification Mapping:** Map each item in `Release Artifacts` to a specific verification step in Section II.C, ensuring every artifact has a clear path to sign-off.
4.  **Risk Identification:** Cross-reference the Focus Areas against common failure modes for desktop GUI applications (e.g., memory leaks, threading issues, complex state management, dependency hell). Use the `Project Context` to contextualize these risks.
5.  **Synthesis:** Assemble the content into the predefined Markdown structure, ensuring tone is professional, concise, and highly actionable.

## 🔗 References (To be included in Skill.md)
*   `references/output-patterns.md`: Detailed examples of successful consolidation plans.
*   `references/risk-taxonomy.md`: Standardized definitions for risk impact and mitigation strategies specific to this domain.