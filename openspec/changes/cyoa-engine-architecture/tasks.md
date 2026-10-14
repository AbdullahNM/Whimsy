## 1. Specification & Architecture Initialization

- [x] 1.1 Initialize OpenSpec framework with Antigravity tool integration
- [x] 1.2 Author comprehensive proposal documenting dual persistence, campaign schemas, UI rendering, and local engine
- [x] 1.3 Author technical design document detailing architectural decisions, trade-offs, and risk mitigations
- [x] 1.4 Formalize capability specifications for dual persistence, schemas, UI engine, and local engine

## 2. Core Python Test Suite Implementation

- [x] 2.1 Implement unit tests for `PromptAssembler` verifying global rules, active turns, and context assembly in `tests/test_prompt_assembler.py`
- [x] 2.2 Implement unit tests for `StateParser` testing XP, currency, and system receipt parsing in `tests/test_state_parser.py`
- [x] 2.3 Implement schema validation tests for campaign configs and living states in `tests/test_schemas.py`
- [x] 2.4 Implement integration tests for `EngineRequestHandler` HTTP endpoints, CORS headers, and generation in `tests/test_engine_server.py`

## 3. JavaScript / UI Test Suite Implementation

- [x] 3.1 Implement Node.js unit tests for markdown parsing, code blocks, task lists, and formatting in `tests/test_markdown_parser.js`
- [x] 3.2 Implement Node.js unit tests for metric extraction, JSON precedence, and regex fallbacks in `tests/test_metrics_extractor.js`

## 4. Test Orchestration & OpenSpec Compliance Verification

- [x] 4.1 Create unified test runner script `tests/run_all_tests.sh`
- [x] 4.2 Execute Python and JavaScript test suites to achieve 100% pass rate
- [x] 4.3 Validate all OpenSpec specifications and changes via `openspec validate --all`
