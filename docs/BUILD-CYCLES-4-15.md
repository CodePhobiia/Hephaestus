# Build Cycles 4-15 Plan

## Cycle 4: Retry & Resilience
- Add retry logic to DeepForge harness (exponential backoff for API failures)
- Add timeout handling to genesis pipeline stages
- Tests for retry behavior

## Cycle 5: Batch Mode
- heph batch: process multiple problems from a file
- Output to directory with individual reports
- Progress tracking

## Cycle 6: Lens Quality
- Lens validation (schema check for all YAML files)
- Lens stats command: heph lenses (count, domains, coverage)
- Tests for lens validation

## Cycle 7: SDK Improvements  
- Async SDK client with proper error handling
- Programmatic access to all pipeline stages
- SDK usage examples

## Cycle 8: Search Quality
- Improve scorer with diversity bonus
- Add negative correlation penalty (too-similar candidates)
- Scorer calibration tests

## Cycle 9: Agent Chat Upgrade
- Wire agent_chat.py to use ConversationRuntime
- Add new tools (export, prior_art, compare)
- Tests for upgraded agent chat

## Cycle 10: Analytics Dashboard
- Invention history analytics (success rates, common domains, cost trends)
- heph stats command
- Data persistence

## Cycle 11: Convergence Detection
- Detect when repeated runs converge on similar solutions
- Track convergence across sessions
- Alert user when hitting convergence ceiling

## Cycle 12: Error Recovery
- Graceful partial results (return best invention even if later stages fail)
- Resume interrupted pipeline runs
- Better error messages with actionable hints

## Cycle 13: Performance
- Parallel candidate scoring (asyncio.gather)
- Cached lens loading
- Pipeline timing instrumentation

## Cycle 14: Test Coverage
- Coverage audit and fill gaps
- Property-based tests for serialization
- Fuzz tests for input validation

## Cycle 15: Final Polish
- Type stubs for public API
- Docstring completeness audit
- CHANGELOG.md
