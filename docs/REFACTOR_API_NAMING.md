# API Naming Refactor Plan

## Problem Statement

The current API naming uses "chat" for multiple unrelated functions:
- LLM conversations (actual chat)
- Job management
- Annotation tasks
- Email configuration
- Model parameters

This creates confusion and violates the principle of clear, function-based naming.

## Current Architecture

```
chat_api.py (port 9001) handles:
├── /chat/init, /chat/message     → LLM conversations
├── /chat/jobs/*                  → Job management
├── /chat/annotate*               → Annotation tasks
├── /chat/email-config            → Email settings
├── /chat/model-parameters/*      → Model config
├── /chat/resources               → Resource monitoring
└── /chat/download/*              → File downloads
```

## Proposed Architecture

### Option A: Functional Grouping (Recommended)

```
core-api.py (port 9001) handles:
├── /api/conversations/*          → LLM chat history
│   ├── POST /api/conversations/init
│   ├── POST /api/conversations/message
│   ├── GET  /api/conversations/{id}
│   └── DELETE /api/conversations/{id}
│
├── /api/jobs/*                   → Job management
│   ├── GET    /api/jobs
│   ├── GET    /api/jobs/{id}
│   ├── DELETE /api/jobs/{id}
│   └── DELETE /api/jobs/completed
│
├── /api/annotations/*            → Annotation tasks
│   ├── POST /api/annotations/manual
│   ├── POST /api/annotations/csv
│   ├── GET  /api/annotations/{id}/status
│   └── GET  /api/annotations/{id}/download
│
├── /api/config/*                 → Configuration
│   ├── GET  /api/config/email
│   ├── GET  /api/config/models
│   └── GET  /api/config/resources
│
└── /api/model-params/*           → Model parameters
    ├── GET  /api/model-params
    ├── POST /api/model-params
    ├── POST /api/model-params/reset
    └── POST /api/model-params/preset/{name}
```

### Option B: Microservices Split

Split `chat_api.py` into separate services:

```
conversation-api.py (port 9001)   → LLM chat only
jobs-api.py (port 9005)           → Job management
annotation-api.py (port 9006)     → Annotation orchestration
```

**Pros:** Better separation of concerns, independent scaling
**Cons:** More complexity, more ports to manage, more cloudflare rules

## Files Requiring Changes

### Backend Changes

1. **`chat_api.py`** → Rename to `core_api.py`
   - Update all route decorators
   - Update function names for clarity

2. **`runner_service.py`**
   - Update any references to chat service endpoints

3. **`llm_assistant.py`**
   - Update any cross-service calls

### Frontend Changes

4. **`webapp/server.py`**
   - Update all proxy route paths
   - Update `CHAT_SERVICE_URL` variable name to `CORE_API_URL`

5. **`webapp/static/app.js`**
   - Update all `fetch()` URLs
   - Search and replace `/api/chat/` → `/api/`
   - Update variable names referencing "chat"

### Infrastructure Changes

6. **`~/.cloudflared/config.yml`**
   - Update path rules:
   ```yaml
   # Before
   - hostname: dev-llm.amphoraxe.ca
     path: /chat/*
     service: http://localhost:9001

   # After (if keeping /chat/* for conversations only)
   - hostname: dev-llm.amphoraxe.ca
     path: /api/conversations/*
     service: http://localhost:9001
   ```

7. **LaunchAgent plist files**
   - Rename `com.amplm.chat.dev.plist` → `com.amplm.core.dev.plist`
   - Update internal references

### Documentation Changes

8. **`MEMORY.md`** - Update API endpoint references
9. **`QUALITY_SCORES.md`** - Update if API endpoints mentioned
10. **Any README files** - Update API documentation

## Migration Strategy

### Phase 1: Add New Routes (Non-Breaking)
1. Add new routes alongside old ones
2. Old routes continue to work
3. Test new routes thoroughly

### Phase 2: Update Frontend
1. Update app.js to use new routes
2. Update server.py proxy paths
3. Test full flow

### Phase 3: Update Infrastructure
1. Update cloudflared config
2. Update launchd plist files
3. Test with fresh restart

### Phase 4: Deprecate Old Routes
1. Add deprecation warnings to old routes
2. Log usage of old routes
3. After 1-2 weeks, remove old routes

## Route Mapping Reference

| Current Route | New Route | Service |
|--------------|-----------|---------|
| `/chat/init` | `/api/conversations/init` | core-api |
| `/chat/message` | `/api/conversations/message` | core-api |
| `/chat/conversations/{id}` | `/api/conversations/{id}` | core-api |
| `/chat/jobs` | `/api/jobs` | core-api |
| `/chat/jobs/{id}` | `/api/jobs/{id}` | core-api |
| `/chat/jobs/completed` | `/api/jobs/completed` | core-api |
| `/chat/annotate` | `/api/annotations/manual` | core-api |
| `/chat/annotate-csv` | `/api/annotations/csv` | core-api |
| `/chat/annotate-csv-status/{id}` | `/api/annotations/{id}/status` | core-api |
| `/chat/download/{id}` | `/api/annotations/{id}/download` | core-api |
| `/chat/email-config` | `/api/config/email` | core-api |
| `/chat/resources` | `/api/config/resources` | core-api |
| `/chat/models` | `/api/config/models` | core-api |
| `/chat/model-parameters` | `/api/model-params` | core-api |
| `/chat/model-parameters/reset` | `/api/model-params/reset` | core-api |
| `/chat/model-parameters/preset/{name}` | `/api/model-params/preset/{name}` | core-api |

## Estimated Effort

- **Backend route changes:** 2-3 hours
- **Frontend updates:** 2-3 hours
- **Infrastructure updates:** 1 hour
- **Testing:** 2-3 hours
- **Total:** ~8-12 hours

## Priority

**Medium** - Not blocking functionality, but improves maintainability and developer experience. Consider doing during a quieter period or as part of a larger refactor.

## Notes

- Keep backward compatibility during transition
- Update any external documentation or API consumers
- Consider adding OpenAPI/Swagger documentation during this refactor
