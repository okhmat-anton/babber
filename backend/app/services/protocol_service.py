"""
Service for managing default thinking protocols.
Creates the standard protocols on first startup.
"""

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.mongodb.models import MongoThinkingProtocol
from app.mongodb.services import ThinkingProtocolService, AgentProtocolService


DEFAULT_PROTOCOLS = [
    # ═══════════════════════════════════════════════════════════
    # LOW-LEVEL SPECIALIZED PROTOCOLS
    # ═══════════════════════════════════════════════════════════
    {
        "name": "Standard Problem Solving",
        "description": "Universal step-by-step reasoning: pick a task → analyze → plan → implement in a loop → output result",
        "type": "standard",
        "is_default": True,
        "steps": [
            {
                "id": "s_0_todo",
                "type": "todo",
                "name": "Create Task List",
                "category": "planning",
                "instruction": "Break down the request into clear, actionable tasks. Create a structured todo list to track progress through each task.",
            },
            {
                "id": "s_1_analyze",
                "type": "action",
                "name": "Analyze Requirements",
                "category": "analysis",
                "instruction": "Carefully read and understand what is being asked. Identify:\n- Inputs and expected outputs\n- Constraints and limitations\n- Success criteria\n- Edge cases to consider",
            },
            {
                "id": "s_2_plan",
                "type": "action",
                "name": "Propose Solutions",
                "category": "planning",
                "instruction": "Generate 2-3 possible approaches to solve the problem. For each approach:\n- Describe the strategy briefly\n- List pros and cons\n- Estimate complexity\nChoose the best approach and explain why.",
            },
            {
                "id": "s_3_loop",
                "type": "loop",
                "name": "Implementation Cycle",
                "category": "execution",
                "instruction": "Iteratively implement and refine the solution until it meets the success criteria or maximum iterations are reached.",
                "max_iterations": 5,
                "exit_condition": "Solution passes all checks and meets success criteria",
                "steps": [
                    {
                        "id": "s_3_0_impl",
                        "type": "action",
                        "name": "Implement",
                        "instruction": "Execute the chosen approach. Write code, produce output, or perform the required action. Focus on correctness first, then optimize.",
                    },
                    {
                        "id": "s_3_1_verify",
                        "type": "action",
                        "name": "Verify",
                        "instruction": "Check the result against success criteria. Look for errors, edge cases, and missing requirements. Test with different inputs if applicable.",
                    },
                    {
                        "id": "s_3_2_decide",
                        "type": "decision",
                        "name": "Evaluate Result",
                        "instruction": "Does the solution meet all requirements?",
                        "exit_condition": "If YES → exit loop and proceed to output. If NO → identify what needs to change and continue loop.",
                    },
                ],
            },
            {
                "id": "s_4_output",
                "type": "action",
                "name": "Output Result",
                "category": "output",
                "instruction": "Present the final result clearly:\n- Summarize what was done\n- Show the solution/output\n- Note any limitations or caveats\n- Suggest follow-up actions if relevant",
            },
        ],
    },
    {
        "name": "Research & Analysis",
        "description": "Deep research protocol: gather information → analyze → synthesize → conclude",
        "type": "standard",
        "is_default": False,
        "steps": [
            {
                "id": "r_0_scope",
                "type": "action",
                "name": "Define Scope",
                "category": "planning",
                "instruction": "Clearly define the research question or analysis goal. Identify what information is needed and what sources to use.",
            },
            {
                "id": "r_1_gather",
                "type": "loop",
                "name": "Information Gathering",
                "category": "execution",
                "instruction": "Collect relevant information from available sources.",
                "max_iterations": 3,
                "exit_condition": "Sufficient information gathered to answer the question",
                "steps": [
                    {
                        "id": "r_1_0_search",
                        "type": "action",
                        "name": "Search & Read",
                        "instruction": "Search for relevant information. Read and extract key facts, data points, and perspectives.",
                    },
                    {
                        "id": "r_1_1_check",
                        "type": "decision",
                        "name": "Sufficiency Check",
                        "instruction": "Is there enough information to form a well-supported conclusion?",
                        "exit_condition": "If YES → exit loop. If NO → identify gaps and search for more.",
                    },
                ],
            },
            {
                "id": "r_2_analyze",
                "type": "action",
                "name": "Analyze & Synthesize",
                "category": "analysis",
                "instruction": "Organize and analyze the gathered information:\n- Identify patterns and trends\n- Compare different perspectives\n- Note contradictions or gaps\n- Draw connections between data points",
            },
            {
                "id": "r_3_conclude",
                "type": "action",
                "name": "Formulate Conclusions",
                "category": "output",
                "instruction": "Present clear, well-supported conclusions:\n- State main findings\n- Provide evidence and reasoning\n- Acknowledge uncertainties\n- Recommend next steps",
            },
        ],
    },
    {
        "name": "Programmer",
        "description": "Write clean, tested code — translates specifications into working implementation",
        "type": "standard",
        "is_default": False,
        "steps": [
            {
                "id": "prog_0_understand",
                "type": "action",
                "name": "Understand Requirements",
                "category": "analysis",
                "instruction": "Parse the task specification. Identify:\n- Programming language / framework\n- Input/output contract\n- Performance requirements\n- Dependencies and integrations\n- Coding style and conventions to follow",
            },
            {
                "id": "prog_1_design",
                "type": "action",
                "name": "Design Solution",
                "category": "planning",
                "instruction": "Design the solution architecture:\n- Data structures and models\n- Key functions/classes and their responsibilities\n- API contracts if applicable\n- Error handling strategy\nKeep it simple — avoid over-engineering.",
            },
            {
                "id": "prog_2_implement",
                "type": "loop",
                "name": "Code & Refine",
                "category": "execution",
                "instruction": "Write the code iteratively. Each iteration should produce working code.",
                "max_iterations": 3,
                "exit_condition": "Code is complete, handles edge cases, and follows best practices",
                "steps": [
                    {
                        "id": "prog_2_0_write",
                        "type": "action",
                        "name": "Write Code",
                        "instruction": "Implement the solution. Write clear, well-commented code. Use meaningful variable names. Follow the language's idioms and conventions.",
                    },
                    {
                        "id": "prog_2_1_review",
                        "type": "action",
                        "name": "Self-Review",
                        "instruction": "Review your own code:\n- Are there bugs or logic errors?\n- Are edge cases handled?\n- Is error handling sufficient?\n- Is the code readable and maintainable?\n- Are there any security concerns?",
                    },
                    {
                        "id": "prog_2_2_check",
                        "type": "decision",
                        "name": "Quality Check",
                        "instruction": "Is the code production-ready?",
                        "exit_condition": "If YES → exit. If NO → fix issues and iterate.",
                    },
                ],
            },
            {
                "id": "prog_3_deliver",
                "type": "action",
                "name": "Deliver Code",
                "category": "output",
                "instruction": "Present the final code:\n- Use project_file_write skill to save code files\n- Explain key design decisions\n- Document usage (how to run, API endpoints, etc.)\n- Note any TODOs or known limitations\n\nSignal completion: <<<DELEGATE_DONE:Code implemented and saved>>>",
            },
        ],
    },
    {
        "name": "Tester",
        "description": "Verify correctness — write and run tests, check edge cases, ensure quality",
        "type": "standard",
        "is_default": False,
        "steps": [
            {
                "id": "test_0_analyze",
                "type": "action",
                "name": "Analyze What to Test",
                "category": "analysis",
                "instruction": "Examine the code/feature to be tested:\n- Read existing code using project_file_read or file_read skills\n- Identify all public interfaces and functions\n- Map out normal flows, edge cases, and error scenarios\n- Determine test strategy (unit, integration, E2E)",
            },
            {
                "id": "test_1_write",
                "type": "action",
                "name": "Write Tests",
                "category": "execution",
                "instruction": "Create comprehensive test cases:\n- Happy path tests for core functionality\n- Edge case tests (empty input, large input, null values)\n- Error handling tests (invalid input, missing dependencies)\n- Boundary condition tests\nSave test files using project_file_write skill.",
            },
            {
                "id": "test_2_run",
                "type": "loop",
                "name": "Test Execution Cycle",
                "category": "execution",
                "instruction": "Run tests and fix any issues found.",
                "max_iterations": 3,
                "exit_condition": "All tests pass or critical issues are documented",
                "steps": [
                    {
                        "id": "test_2_0_exec",
                        "type": "action",
                        "name": "Run Tests",
                        "instruction": "Execute the tests using shell_exec or code_execute skill. Collect results: passed, failed, errors.",
                    },
                    {
                        "id": "test_2_1_eval",
                        "type": "decision",
                        "name": "Evaluate Results",
                        "instruction": "Did all tests pass? Are there failures that indicate real bugs vs test issues?",
                        "exit_condition": "If all pass → exit. If failures → analyze and either fix test or report bug.",
                    },
                ],
            },
            {
                "id": "test_3_report",
                "type": "action",
                "name": "Test Report",
                "category": "output",
                "instruction": "Deliver a test report:\n- Total tests: passed / failed / skipped\n- Coverage of key scenarios\n- Bugs found (if any) with reproduction steps\n- Recommendations for additional testing\n\nSignal completion: <<<DELEGATE_DONE:Testing complete — X/Y tests passed>>>",
            },
        ],
    },
    {
        "name": "Code Reviewer",
        "description": "Review code for quality, correctness, security, and best practices",
        "type": "standard",
        "is_default": False,
        "steps": [
            {
                "id": "rev_0_read",
                "type": "action",
                "name": "Read Code",
                "category": "analysis",
                "instruction": "Read all relevant code files using project_file_read or file_read skills. Understand:\n- Overall architecture and design patterns\n- Data flow and control flow\n- Dependencies and imports\n- Configuration and environment usage",
            },
            {
                "id": "rev_1_check",
                "type": "action",
                "name": "Quality Analysis",
                "category": "analysis",
                "instruction": "Evaluate the code on multiple dimensions:\n- **Correctness**: Logic errors, off-by-one, race conditions\n- **Security**: Injection, auth bypass, data exposure, path traversal\n- **Performance**: N+1 queries, unnecessary allocations, blocking I/O\n- **Readability**: Naming, structure, comments, complexity\n- **Maintainability**: SOLID principles, DRY, proper abstractions\n- **Error Handling**: Missing try/catch, unhandled edge cases",
            },
            {
                "id": "rev_2_report",
                "type": "action",
                "name": "Review Report",
                "category": "output",
                "instruction": "Produce a structured code review:\n- **Critical issues** (must fix before merge)\n- **Warnings** (should fix, potential problems)\n- **Suggestions** (nice-to-have improvements)\n- **Positive notes** (good practices observed)\n\nFor each issue: file, line/area, description, suggested fix.\n\nSignal completion: <<<DELEGATE_DONE:Code review complete — N critical, M warnings>>>",
            },
        ],
    },
    {
        "name": "Creative Writer",
        "description": "Generate creative content — texts, ideas, narratives, brainstorming",
        "type": "standard",
        "is_default": False,
        "steps": [
            {
                "id": "cw_0_brief",
                "type": "action",
                "name": "Understand Brief",
                "category": "analysis",
                "instruction": "Analyze the creative brief:\n- Content type (article, story, copy, brainstorm, etc.)\n- Target audience\n- Tone and style requirements\n- Length and format constraints\n- Key messages or themes to convey",
            },
            {
                "id": "cw_1_ideate",
                "type": "action",
                "name": "Ideation",
                "category": "planning",
                "instruction": "Generate multiple creative directions:\n- Brainstorm 3-5 different angles or approaches\n- Consider unexpected perspectives\n- Think about emotional resonance\n- Select the strongest direction and explain why",
            },
            {
                "id": "cw_2_create",
                "type": "loop",
                "name": "Draft & Refine",
                "category": "execution",
                "instruction": "Create the content iteratively, refining with each pass.",
                "max_iterations": 3,
                "exit_condition": "Content meets the brief requirements and quality bar",
                "steps": [
                    {
                        "id": "cw_2_0_draft",
                        "type": "action",
                        "name": "Draft",
                        "instruction": "Write the content. Focus on capturing the right tone, delivering key messages, and engaging the audience.",
                    },
                    {
                        "id": "cw_2_1_polish",
                        "type": "action",
                        "name": "Polish",
                        "instruction": "Refine the draft:\n- Improve flow and readability\n- Strengthen weak sections\n- Eliminate redundancy\n- Ensure consistency of voice and style",
                    },
                ],
            },
            {
                "id": "cw_3_deliver",
                "type": "action",
                "name": "Deliver Content",
                "category": "output",
                "instruction": "Present the final content with:\n- The finished piece\n- Brief notes on creative choices made\n- Suggestions for variations or follow-up content\n\nSignal completion: <<<DELEGATE_DONE:Content created>>>",
            },
        ],
    },

    {
        "name": "Deep Task Decomposition",
        "description": "Break down complex tasks into atomic sub-tasks — eat the elephant piece by piece. Recursively decomposes until every item is a simple, concrete action.",
        "type": "standard",
        "is_default": False,
        "steps": [
            {
                "id": "dtd_0_understand",
                "type": "action",
                "name": "Understand the Goal",
                "category": "analysis",
                "model_role": "task_decomposition",
                "instruction": (
                    "Analyze the task at a high level:\n"
                    "1. **What** is the end goal? What does 'done' look like?\n"
                    "2. **Why** is this needed? Understanding purpose helps decompose correctly.\n"
                    "3. **Scope** — What is included and what is explicitly out of scope?\n"
                    "4. **Constraints** — Time, technology, dependencies, prerequisites.\n"
                    "5. **Inputs available** — What do we already have to work with?\n"
                    "6. **Risks** — What could go wrong? What unknowns exist?\n"
                    "\n"
                    "Complexity assessment:\n"
                    "  - **Trivial** → No decomposition needed, just do it.\n"
                    "  - **Simple** → 2-5 clear steps, light decomposition.\n"
                    "  - **Medium** → Multiple components, needs structured breakdown.\n"
                    "  - **Complex** → Multiple layers, cross-cutting concerns, deep decomposition required."
                ),
            },
            {
                "id": "dtd_1_first_level",
                "type": "action",
                "name": "First Level Breakdown",
                "category": "planning",
                "model_role": "task_decomposition",
                "instruction": (
                    "Break the task into major components or phases (3-7 top-level items).\n"
                    "Each component should represent a distinct, meaningful chunk of work.\n"
                    "\n"
                    "For each component identify:\n"
                    "- **Name** — Short, descriptive label\n"
                    "- **Purpose** — What this component achieves\n"
                    "- **Dependencies** — What must be done before this\n"
                    "- **Estimated complexity** — Trivial / Simple / Medium / Complex\n"
                    "\n"
                    "Order components by dependency (things that need to happen first go first).\n"
                    "This is the skeleton — we will decompose each component further."
                ),
            },
            {
                "id": "dtd_2_deep_loop",
                "type": "loop",
                "name": "Deep Decomposition",
                "category": "planning",
                "instruction": "For each component marked as Medium or Complex, recursively break it down further until every sub-task is atomic.",
                "max_iterations": 5,
                "exit_condition": "Every item in the task list is an atomic action (can be done in 1-2 simple steps with no ambiguity)",
                "steps": [
                    {
                        "id": "dtd_2_0_decompose",
                        "type": "action",
                        "name": "Decompose Next Component",
                        "model_role": "task_decomposition",
                        "instruction": (
                            "Take the next non-atomic component and break it into smaller sub-tasks.\n"
                            "\n"
                            "**Atomic task criteria** — a task is atomic when:\n"
                            "- It can be completed in one sitting (minutes, not hours)\n"
                            "- It has a single, clear action (create, read, write, configure, test, etc.)\n"
                            "- The expected output is obvious and verifiable\n"
                            "- No further decisions are needed to execute it\n"
                            "- A junior developer or a focused AI could do it without asking questions\n"
                            "\n"
                            "**Decomposition rules:**\n"
                            "- Each sub-task should be 1 concrete action (not 'implement feature X' but 'create file Y with function Z')\n"
                            "- Include verification steps (e.g., 'run tests', 'check output', 'verify file exists')\n"
                            "- Name tasks as imperative verbs: Create, Write, Add, Configure, Test, Verify, Update\n"
                            "- Preserve dependency order within the component\n"
                            "- If a sub-task is still complex, mark it for further decomposition"
                        ),
                    },
                    {
                        "id": "dtd_2_1_check",
                        "type": "decision",
                        "name": "All Tasks Atomic?",
                        "instruction": "Review the full task list. Are there any remaining items that are not atomic (still too vague, too large, or require further decisions)?",
                        "exit_condition": "If ALL tasks are atomic → exit loop. If any tasks are still complex → continue decomposing.",
                    },
                ],
            },
            {
                "id": "dtd_3_build_plan",
                "type": "todo",
                "name": "Build Execution Plan",
                "category": "planning",
                "instruction": (
                    "Convert the fully decomposed task tree into a flat, ordered execution plan.\n"
                    "\n"
                    "Ordering rules:\n"
                    "- Respect dependencies (prerequisites first)\n"
                    "- Group related tasks together\n"
                    "- Place verification/test steps right after the thing they verify\n"
                    "- Number every task sequentially\n"
                    "\n"
                    "Each task in the todo list should be:\n"
                    "- A single atomic action\n"
                    "- Phrased as an imperative (e.g., 'Create utils.py with helper functions')\n"
                    "- Self-contained — readable without needing surrounding context"
                ),
            },
            {
                "id": "dtd_4_execute",
                "type": "loop",
                "name": "Execute Tasks",
                "category": "execution",
                "instruction": "Work through the todo list task by task. Mark each as done when complete. If a task reveals unexpected complexity, decompose it further before continuing.",
                "max_iterations": 20,
                "exit_condition": "All tasks in the todo list are done or skipped",
                "steps": [
                    {
                        "id": "dtd_4_0_do",
                        "type": "action",
                        "name": "Execute Next Task",
                        "instruction": "Pick the next pending task from the todo list. Execute it. Mark it as done. Update the todo list. If the task is blocked, skip it and note why.",
                    },
                    {
                        "id": "dtd_4_1_verify",
                        "type": "decision",
                        "name": "Check Progress",
                        "instruction": "Is the todo list complete? Are there any blocked or failed tasks that need replanning?",
                        "exit_condition": "If all done → exit. If blocked tasks remain → add decomposed alternatives and continue.",
                    },
                ],
            },
            {
                "id": "dtd_5_summary",
                "type": "action",
                "name": "Deliver Results",
                "category": "output",
                "instruction": (
                    "Present the final results:\n"
                    "1. **Summary** — What was accomplished\n"
                    "2. **Task breakdown** — The decomposition tree (for reference)\n"
                    "3. **Deliverables** — Files created, code written, actions taken\n"
                    "4. **Issues encountered** — Anything that was harder than expected\n"
                    "5. **Remaining items** — Skipped/blocked tasks, if any\n"
                    "\n"
                    "Signal completion: <<<DELEGATE_DONE:Task decomposition and execution complete>>>"
                ),
            },
        ],
    },

    # ═══════════════════════════════════════════════════════════
    # MID-LEVEL ORCHESTRATORS
    # ═══════════════════════════════════════════════════════════
    {
        "name": "Development Orchestrator",
        "description": "Mid-level orchestrator for software development: coordinates coding, testing, and code review",
        "type": "orchestrator",
        "is_default": False,
        "steps": [
            {
                "id": "dev_0_analyze",
                "type": "action",
                "name": "Analyze Development Task",
                "category": "analysis",
                "instruction": "Understand the development request:\n- What needs to be built or changed?\n- What is the existing codebase state? (check files first)\n- What are the technical constraints?\n- How complex is this — simple feature, refactor, or new system?",
            },
            {
                "id": "dev_1_plan",
                "type": "todo",
                "name": "Create Development Plan",
                "category": "planning",
                "instruction": "Break down into development sub-tasks:\n1. Implementation (code writing)\n2. Testing (if applicable)\n3. Code review (if complex)\nCreate a structured todo list for tracking.",
            },
            {
                "id": "dev_2_code",
                "type": "delegate",
                "name": "Implement Code",
                "category": "execution",
                "instruction": "Delegate code implementation to the Programmer protocol. Provide clear specifications:\n- What to build\n- Expected behavior\n- Files and locations\n- Coding conventions to follow",
                "protocol_ids": [],  # Will be filled with Programmer protocol ID
            },
            {
                "id": "dev_3_test",
                "type": "delegate",
                "name": "Test Implementation",
                "category": "verification",
                "instruction": "Delegate testing to the Tester protocol. Specify:\n- What files to test\n- Expected behavior to verify\n- Edge cases to check\nSkip this step for trivial changes.",
                "protocol_ids": [],  # Will be filled with Tester protocol ID
            },
            {
                "id": "dev_4_review",
                "type": "delegate",
                "name": "Review Code Quality",
                "category": "verification",
                "instruction": "Delegate code review to the Code Reviewer protocol for complex changes. Specify:\n- Files to review\n- Key concerns (security, performance, etc.)\nSkip for simple/trivial changes.",
                "protocol_ids": [],  # Will be filled with Code Reviewer protocol ID
            },
            {
                "id": "dev_5_evaluate",
                "type": "loop",
                "name": "Evaluate & Iterate",
                "category": "verification",
                "instruction": "Review all results from coding, testing, and review. If there are issues, re-delegate to fix them.",
                "max_iterations": 2,
                "exit_condition": "All development sub-tasks completed successfully, no critical issues remain",
                "steps": [
                    {
                        "id": "dev_5_0_check",
                        "type": "decision",
                        "name": "Quality Gate",
                        "instruction": "Are all critical issues resolved? Is the code ready for delivery?",
                        "exit_condition": "If YES → deliver. If NO → delegate fixes to Programmer.",
                    },
                ],
            },
            {
                "id": "dev_6_deliver",
                "type": "action",
                "name": "Deliver Results",
                "category": "output",
                "instruction": "Summarize the development work:\n- What was implemented\n- Test results\n- Any remaining TODOs or known issues\n- Files changed\n\nSignal completion: <<<DELEGATE_DONE:Development complete>>>",
            },
        ],
    },

    # ═══════════════════════════════════════════════════════════
    # MASTER ORCHESTRATOR (TOP-LEVEL)
    # ═══════════════════════════════════════════════════════════
    {
        "name": "Master Orchestrator",
        "description": "Top-level orchestrator — analyzes user intent, decomposes complex tasks, delegates to specialized protocols (including mid-level orchestrators), evaluates results, and iterates until the task is fully complete",
        "type": "orchestrator",
        "is_default": False,
        "steps": [
            {
                "id": "mo_0_intent",
                "type": "action",
                "name": "Understand User Intent",
                "category": "analysis",
                "instruction": (
                    "Deeply analyze the user's message to determine:\n"
                    "1. **Primary intent** — What does the user want? (build something, fix something, learn something, create content, analyze data, etc.)\n"
                    "2. **Scope** — Is this a simple question, a single task, or a complex multi-step project?\n"
                    "3. **Domain** — Software development, research, creative work, data analysis, system administration, general knowledge?\n"
                    "4. **Implicit needs** — What the user didn't say but probably expects (e.g., error handling, testing, documentation)\n"
                    "5. **Constraints** — Time, quality, technology, format preferences\n"
                    "\n"
                    "Classify complexity:\n"
                    "  - **Simple** (1 protocol): Direct answer, single-step task\n"
                    "  - **Medium** (1-2 protocols): Multi-step but single domain\n"
                    "  - **Complex** (2+ protocols, possibly hierarchical): Cross-domain, requires planning + multiple delegations"
                ),
            },
            {
                "id": "mo_1_plan",
                "type": "todo",
                "name": "Create Execution Plan",
                "category": "planning",
                "instruction": (
                    "Based on intent analysis, create a strategic plan:\n"
                    "- Break complex tasks into ordered sub-tasks\n"
                    "- For each sub-task, identify which protocol is best suited\n"
                    "- Consider dependencies between sub-tasks (what must happen first?)\n"
                    "- Identify where mid-level orchestrators should be used vs direct protocols\n"
                    "\n"
                    "Create a todo list that tracks the overall progress of all delegations."
                ),
            },
            {
                "id": "mo_2_decide",
                "type": "decision",
                "name": "Select Execution Strategy",
                "category": "planning",
                "instruction": (
                    "Choose the execution strategy:\n"
                    "\n"
                    "**A) Direct handling** — For simple questions, use your own knowledge and skills directly.\n"
                    "   → No delegation needed, just answer.\n"
                    "\n"
                    "**B) Single delegation** — For medium tasks in one domain:\n"
                    "   → Delegate to one specialized protocol (Programmer, Researcher, Writer, etc.)\n"
                    "\n"
                    "**C) Sequential delegation** — For complex tasks:\n"
                    "   → Delegate to multiple protocols in sequence, reviewing results between each\n"
                    "\n"
                    "**D) Orchestrator delegation** — For complex development tasks:\n"
                    "   → Delegate to a mid-level orchestrator (Development Orchestrator) which manages its own sub-delegations\n"
                    "\n"
                    "Explain your choice and proceed."
                ),
                "exit_condition": "Strategy selected, proceed to execution",
            },
            {
                "id": "mo_3_execute",
                "type": "delegate",
                "name": "Execute via Delegation",
                "category": "execution",
                "instruction": (
                    "Delegate to the selected protocol(s). For each delegation:\n"
                    "1. Provide clear, specific context about what needs to be done\n"
                    "2. Include any relevant constraints or requirements\n"
                    "3. Specify expected deliverables\n"
                    "\n"
                    "**Protocol selection guide:**\n"
                    "- Coding task → `Development Orchestrator` (complex) or `Programmer` (simple)\n"
                    "- Bug fixing → `Programmer` + optionally `Tester`\n"
                    "- Complex multi-step task → `Deep Task Decomposition`\n"
                    "- Research question → `Research & Analysis`\n"
                    "- General problem → `Standard Problem Solving`\n"
                    "- Creative writing → `Creative Writer`\n"
                    "- Code quality → `Code Reviewer`\n"
                    "- Testing → `Tester`\n"
                    "\n"
                    "After delegating, wait for <<<DELEGATE_DONE>>> to receive results."
                ),
                "protocol_ids": [],  # Will be filled with ALL protocol IDs
            },
            {
                "id": "mo_4_evaluate",
                "type": "loop",
                "name": "Evaluate & Iterate",
                "category": "verification",
                "instruction": "After each delegation completes, evaluate the results against the original intent.",
                "max_iterations": 3,
                "exit_condition": "All sub-tasks from the plan are completed successfully",
                "steps": [
                    {
                        "id": "mo_4_0_review",
                        "type": "action",
                        "name": "Review Results",
                        "instruction": (
                            "For each completed delegation:\n"
                            "- Does the result meet the requirements?\n"
                            "- Is the quality acceptable?\n"
                            "- Are there gaps or missing pieces?\n"
                            "- Should another protocol be invoked to complement?"
                        ),
                    },
                    {
                        "id": "mo_4_1_decide",
                        "type": "decision",
                        "name": "Next Action",
                        "instruction": (
                            "Based on review:\n"
                            "- **All done** → Exit loop, proceed to synthesis\n"
                            "- **Needs fixing** → Re-delegate to same protocol with feedback\n"
                            "- **Needs more work** → Delegate to next protocol in the plan\n"
                            "- **Wrong approach** → Try a different protocol\n"
                            "Update the todo list with status changes."
                        ),
                        "exit_condition": "All planned work complete and quality is sufficient → exit loop",
                    },
                ],
            },
            {
                "id": "mo_5_synthesize",
                "type": "action",
                "name": "Synthesize & Deliver",
                "category": "output",
                "instruction": (
                    "Compile the final response for the user:\n"
                    "1. **Summary** — What was accomplished (high-level)\n"
                    "2. **Details** — Key results from each delegation\n"
                    "3. **Deliverables** — Files created, code written, answers found\n"
                    "4. **Next steps** — Suggestions for follow-up or improvements\n"
                    "\n"
                    "Present it in a clear, user-friendly format.\n"
                    "The user should not need to understand the internal delegation mechanics."
                ),
            },
        ],
    },
]


async def create_default_protocols(db: AsyncIOMotorDatabase):
    """Create default thinking protocols if they don't exist.
    Also adds any new default protocols that were added after initial setup.
    """
    svc = ThinkingProtocolService(db)
    count = await svc.count()

    if count > 0:
        # Existing installation — check for missing default protocols and add them
        await _ensure_new_default_protocols(db)
        return

    # First-time setup: create all protocols
    proto_map = {}  # name -> MongoThinkingProtocol instance
    for proto_data in DEFAULT_PROTOCOLS:
        proto = MongoThinkingProtocol(
            name=proto_data["name"],
            description=proto_data["description"],
            type=proto_data.get("type", "standard"),
            steps=proto_data["steps"],
            is_default=proto_data.get("is_default", False),
        )
        proto = await svc.create(proto)
        proto_map[proto_data["name"]] = proto

    # Second pass: wire orchestrator delegate steps to actual protocol IDs
    # Collect IDs by category
    all_standard_ids = [str(p.id) for name, p in proto_map.items() if p.type == "standard"]
    programmer_id = str(proto_map["Programmer"].id) if "Programmer" in proto_map else None
    tester_id = str(proto_map["Tester"].id) if "Tester" in proto_map else None
    reviewer_id = str(proto_map["Code Reviewer"].id) if "Code Reviewer" in proto_map else None

    # Wire Development Orchestrator → Programmer, Tester, Code Reviewer
    dev_orch = proto_map.get("Development Orchestrator")
    if dev_orch:
        dev_child_ids = [pid for pid in [programmer_id, tester_id, reviewer_id] if pid]
        steps = list(dev_orch.steps)
        for step in steps:
            if step.get("type") == "delegate":
                step_name = step.get("name", "")
                if "Implement" in step_name and programmer_id:
                    step["protocol_ids"] = [programmer_id]
                elif "Test" in step_name and tester_id:
                    step["protocol_ids"] = [tester_id]
                elif "Review" in step_name and reviewer_id:
                    step["protocol_ids"] = [reviewer_id]
                else:
                    step["protocol_ids"] = dev_child_ids
        await svc.update(dev_orch.id, {"steps": steps})

    # Wire Master Orchestrator → ALL protocols (both standard and mid-level orchestrators)
    master = proto_map.get("Master Orchestrator")
    if master:
        all_ids = [str(p.id) for name, p in proto_map.items() if name != "Master Orchestrator"]
        steps = list(master.steps)
        for step in steps:
            if step.get("type") == "delegate":
                step["protocol_ids"] = all_ids
        await svc.update(master.id, {"steps": steps})

    # Keep backward compat: wire the old Adaptive Orchestrator too (if present)
    adaptive = proto_map.get("Adaptive Orchestrator")
    if adaptive:
        steps = list(adaptive.steps)
        for step in steps:
            if step.get("type") == "delegate":
                step["protocol_ids"] = all_standard_ids
        await svc.update(adaptive.id, {"steps": steps})


async def _ensure_new_default_protocols(db: AsyncIOMotorDatabase):
    """Add any default protocols that are missing from an existing installation.
    This allows new protocol templates to be auto-created on server restart
    without overwriting user-modified protocols.
    """
    svc = ThinkingProtocolService(db)
    existing = await svc.get_all(limit=500)
    existing_names = {p.name for p in existing}

    created = []
    for proto_data in DEFAULT_PROTOCOLS:
        if proto_data["name"] not in existing_names:
            proto = MongoThinkingProtocol(
                name=proto_data["name"],
                description=proto_data["description"],
                type=proto_data.get("type", "standard"),
                steps=proto_data["steps"],
                is_default=proto_data.get("is_default", False),
            )
            proto = await svc.create(proto)
            created.append(proto)

    if created:
        names = ", ".join(p.name for p in created)
        print(f"[PROTOCOLS] Added {len(created)} new default protocol(s): {names}")

        # Wire new protocols into existing orchestrators' delegate steps
        all_protos = await svc.get_all(limit=500)
        all_non_master_ids = [str(p.id) for p in all_protos if p.name != "Master Orchestrator"]

        master = next((p for p in all_protos if p.name == "Master Orchestrator"), None)
        if master:
            steps = list(master.steps)
            for step in steps:
                if step.get("type") == "delegate":
                    step["protocol_ids"] = all_non_master_ids
            await svc.update(master.id, {"steps": steps})


async def deduplicate_protocols(db: AsyncIOMotorDatabase):
    """
    Remove duplicate ThinkingProtocol records (same name + type).
    Keeps the protocol created first; deletes the rest.
    Re-points orphaned agent_protocols to the surviving record.
    """
    svc = ThinkingProtocolService(db)
    ap_svc = AgentProtocolService(db)

    # Find duplicate groups using aggregation pipeline
    pipeline = [
        {"$group": {"_id": {"name": "$name", "type": "$type"}, "count": {"$sum": 1}}},
        {"$match": {"count": {"$gt": 1}}},
    ]
    cursor = svc.collection.aggregate(pipeline)
    dup_groups = await cursor.to_list(length=500)
    if not dup_groups:
        return 0

    removed = 0
    for group in dup_groups:
        name = group["_id"]["name"]
        ptype = group["_id"]["type"]

        # Get all protocols in this group, ordered by created_at (keep oldest)
        protos = await svc.get_all(
            filter={"name": name, "type": ptype},
            limit=100,
        )
        protos.sort(key=lambda p: p.created_at or "")

        keeper = protos[0]
        duplicates = protos[1:]

        for dup in duplicates:
            # Re-point any agent_protocol references to the keeper
            agent_protos = await ap_svc.get_all(filter={"protocol_id": dup.id}, limit=500)
            for ap in agent_protos:
                # Check if keeper is already assigned to this agent
                existing = await ap_svc.find_one({
                    "agent_id": ap.agent_id,
                    "protocol_id": keeper.id,
                })
                if existing:
                    await ap_svc.delete(ap.id)
                else:
                    await ap_svc.update(ap.id, {"protocol_id": keeper.id})

            await svc.delete(dup.id)
            removed += 1

    return removed
