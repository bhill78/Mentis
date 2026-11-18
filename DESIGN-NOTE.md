# Governance forms — round 4 preview

Open `governance.html` directly from a `file://` URL. It is one self-contained, interactive HTML file: no server, build, dependencies or network. Creation is simulated in the open tab only. This is a design preview for the owner's approval; it does not implement or deploy the product redesign.

The owner asked for task-specific layouts that use the horizontal workspace, following round 3's plain-language choice, composing beside the record as it will read, creation without a separate review step, and readable draft protection. This round carries those behaviours into four different record shapes.

## Four layouts, four jobs

| Kind | Organised around | Why this layout uses the width |
| --- | --- | --- |
| Decision | Writing a settled question and its answer | A guidance column, a generous writing area, and a record preview share the workspace. Its two fields do not become a long, sparse form. The guidance helps distinguish recording a choice from asking somebody to make one. |
| Conversation Instruction | Describing how people should act in one conversation | Conversation context frames the short writing task. Guidance explains that it applies whoever is acting and whatever Persona they wear. The preview shows the instruction in that context while it is written. |
| Discipline | Describing a practice, the tools it uses, and how to verify the work | Principles and procedure have a substantial writing area beside tools and tool use. Inputs, outputs, verification and limitations sit below as the practice's operating contract. The full record remains beside that editing surface. |
| Workflow | Building and checking an ordered sequence of activities | Overview, Activities and Finish & handoff organise the task. In Activities, an ordered navigator sits beside the selected activity editor; the record preview remains in its own column. The author can see where the selected work belongs, change its order and check the resulting sequence. |

The entry cards explain what each kind is, when to use it, and a realistic example before opening an empty composer. **Load realistic example** is an explicit action, so fixture wording cannot be mistaken for the author's own draft. All four use the same visual language, draft warning and preview-to-created-record path.

At 1440px, the large kinds spend most of the workspace on their composing task, while keeping a readable preview column. At 1024px, editing and preview remain side by side. At 375px, the layout becomes one column: writing precedes the preview, with **Write** and **Live preview** jump links. On desktop, the preview scrolls independently so a long Workflow or Discipline does not push creation or the rest of the record out of reach. There is no separate review screen.

## Grounding and field coverage

The design starts with the live `kinds` declarations and real records, rather than a generic field stack. The exact declared field names are retained; plain-language labels explain their purpose.

| Kind | Fields and input shapes |
| --- | --- |
| Decision | `text`, `about`: the settled question and answer, with an optional subject. |
| Conversation Instruction | `text`, `about`: behaviour for this conversation, with an optional subject. Conversation placement is context for the record, not a third body field. |
| Discipline | `name` and `about` are lines; `text` is substantial prose (12 rows); `tools` is a list, one per line; `tool_use` is prose (6 rows); `requires` selects runtime capabilities; `inputs`, `outputs`, `verification`, `limits` are prose. All ten fields are represented. |
| Workflow | `name`, `about` are lines; `projects` is a list; `text` is prose (8 rows); `activities` is an ordered composite editor; `decisions` is a list; `done_when`, `evidence`, `interrupted` are prose; `carrier` selects a participant; `persona` selects a Persona; `requires` selects runtime capabilities. All twelve fields are represented. |

Each Workflow activity contains what happens, who carries it (role, participant and Persona where supplied), the Disciplines given to delegated work, and when it is done. Activity editing offers adding, moving up or down, removal with confirmation, and previous/next navigation. Sequence position is always visible. These describe work; they do not schedule it or move it forward automatically.

The realistic examples are grounded in these records:

- **Workflow:** standing **Software change**, `ent-5b42a95dbda1`. The example has ten activities, reserved decisions, a completion condition, evidence, continuation after interruption and carrier defaults. It tests the sequence editor at the scale the real form needs.
- **Discipline:** standing **CLI and MARS development**, `ent-80392167cca0`. All ten populated fields inform the practice layout, including the long procedure and tool-use sections, tools list and runtime capability requirement.
- **Decision:** `ent-5717950cf451`, the settled meaning of “introduced by this work.” It demonstrates that a decision may be a paragraph of exact wording, not a short title plus a status.
- **Conversation Instruction:** `ent-16490bdfadf4`, **welcome tour**. Its short instruction tells a guide what to explain and what to suggest next, within one conversation.

Owner direction was read in `ent-d6de4221a3af` and `ent-7318a26477da`. Round 3's HTML (`adm-4334ebd69892`) and design note (`adm-055574751f09`) supply the carried-over interaction direction. The preview does not claim to look up live identities or grant authority by naming tools, capabilities, participants or Personas.

## Draft safety and creation

**Close** and **Change kind** protect every changed draft, including a part-written activity or list row. The warning is a separate readable card with **Keep editing** and **Discard draft**. Keep editing and Escape return to the same draft and values. Discard is explicit. Merely opening an empty composer can be cancelled without a warning.

The preview updates as fields, list values, activity details and ordering change. Creation uses that same record representation and is simulated only. The default is a proposal with no standing; explicit owner establishment is a deliberate separate choice. Recording a Decision does not answer or close an open request. The created result is reachable directly from composing, and **Create another** begins a fresh kind choice.

Drafts are held in tab memory. The in-page warning protects the prototype's navigation; closing or reloading a dirty tab uses the browser's native leave warning. The preview is not durable draft storage.

## Click routes

Start from a freshly opened file. Any listed composer route can use typed text instead of the example.

| State | Click route |
| --- | --- |
| Kind choice | Open `governance.html`. After a result, **Create another** returns here. |
| Decision composing | **Write a decision** → **Load realistic example**. Edit the settled question and answer or its subject; the preview changes immediately. |
| Conversation Instruction composing | **Write an instruction** → **Load realistic example**. Edit the instruction within its conversation context. |
| Discipline composing | **Describe a discipline** → **Load realistic example**. Edit principles beside tools/tool use; scroll to inputs, outputs, verification and limitations. |
| Workflow composing | **Build a workflow** → **Load realistic example** → **Activities**. Select any of the ten activities to edit it beside the sequence and record preview. |
| Workflow overview | From Workflow, **Overview**. Edit name, applicability, projects and the description of how the work proceeds. |
| Workflow completion and defaults | From Workflow, **Finish & handoff**. Edit reserved decisions, completion, supporting evidence, interruption, carrier, Persona and capabilities. |
| Add and edit an activity | Workflow → **Activities** → **Add activity** → type into **What happens**, **Who carries it**, **Disciplines** and **Done when**. |
| Reorder in context | Select an activity in the sequence → **Move up** or **Move down**. Use **Previous** or **Next** to inspect its neighbours. The preview follows the same order. |
| Remove an activity | Select an activity → **Remove activity** → confirm removal in the warning card. Cancel keeps it. |
| Leave warning | Any composer → type, edit a list row or start an activity → **Close**. **Change kind** reaches the same draft warning. |
| Preserved draft | Leave warning → **Keep editing**. The typed content, list rows and selected activity remain. Escape also keeps the draft. |
| Discarded draft | Leave warning → **Discard draft**. No created result is produced from the discarded draft. |
| Created result, each kind | Open that kind → **Load realistic example** → **Create** for that kind in the preview panel. The created card shows the same record. |
| Narrow writing and preview | Set the browser viewport to 375px, then take any composer route. Use **Live preview** to jump to the record and **Write** to return. |

Desktop screenshots use 1440 × 1000; the intermediate layout uses 1024 × 1000; narrow screenshots use 375 × 900. All states above are reachable by clicks, without URL flags, a console or the verifier.

## Status and boundaries

This is a prototype candidate. Owner approval is not claimed, and earlier rounds are not closed or superseded by an unapproved preview. Product source, TEST and DAY-TO-DAY, deployments, Manage Sources, conversation refresh, typography, selection and list padding are outside this work.

The separate verification report names the tested commit, browser, check counts, screenshots, and any limitation. This note describes the design and routes; it is not a claim that a browser check passed.
