# <!-- Change Name --> Implementation Plan

**Goal:** <!-- One sentence describing what this builds -->

**Architecture:** <!-- 2-3 sentences about approach -->

## Global Constraints

<!-- Project-wide requirements copied verbatim from the specs and design:
     version floors, dependency limits, naming rules, platform requirements.
     One line each. Every task's requirements implicitly include this section. -->

---

## Task 1: <!-- Component Name -->

**Files:**
- Create: `<!-- exact/path/to/file -->`
- Test: `<!-- exact/path/to/test -->`

**Interfaces:**
- Consumes: <!-- exact signatures this task uses from earlier tasks -->
- Produces: <!-- exact function names, parameter and return types later tasks rely on -->

**Test kind:** SPEC TEST <!-- or CHARACTERIZATION, if pinning existing behavior -->

- [ ] **Step 1: Write the failing test**

<!-- actual test code, not a description -->

- [ ] **Step 2: Run the test and watch it fail**

Run: `<!-- exact command -->`
Expected: FAIL with `<!-- expected message -->`

- [ ] **Step 3: Write the minimal implementation**

<!-- actual code, not a description -->

- [ ] **Step 4: Run the test and watch it pass**

Run: `<!-- exact command -->`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add <!-- paths --> && git commit -m "<!-- message -->"
```

<!--
FORMAT RULES — these are machine contracts, not style:
  1. Task headings MUST be `## Task N: <name>`.
     superpowers' task-brief awk matches ^#+[ \t]+Task[ \t]+[0-9]+ and exits 3 otherwise.
  2. Every checkbox MUST start at column 0.
     OpenSpec's checkbox regexes anchor ^ directly to [-*]; indented checkboxes are invisible.
  3. No placeholders in a finished plan. "TBD", "add error handling", "similar to Task N",
     and steps without code are plan failures — the implementer sees only their own task.
-->
