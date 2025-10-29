# Floor Plan Agent API - Modularized Architecture

## Overview
This is a modularized version of the Floor Plan Agent API that provides AI-powered document analysis and annotation capabilities. The application has been reorganized into a clean, maintainable modular structure.

## Architecture

### Module Structure
```
modules/
├── config/          # Configuration and utilities
│   ├── settings.py  # Application settings and environment variables
│   ├── utils.py     # Utility functions
│   └── __init__.py
├── database/        # Database models and operations
│   ├── models.py    # User and chat message models, database operations
│   └── __init__.py
├── auth/           # Authentication services
│   ├── service.py   # Authentication business logic
│   ├── endpoints.py # Authentication API endpoints
│   └── __init__.py
├── pdf_processing/ # PDF processing and RAG
│   ├── service.py   # PDF indexing and RAG services
│   ├── endpoints.py # Document management API endpoints
│   └── __init__.py
├── agent/          # AI agent workflow
│   ├── tools.py     # LangChain tools for floor plan processing
│   ├── workflow.py  # Agent workflow and memory management
│   └── __init__.py
├── api/            # API endpoints
│   ├── agent_endpoints.py    # Unified agent and chat endpoints
│   ├── general_endpoints.py  # General utility endpoints
│   └── __init__.py
└── __init__.py
```

## Key Features

### 1. Enhanced Authentication System
- **Regular Signup/Login**: Uses firstname, lastname, email, password with validation
- **Google OAuth**: Secure Google sign-in/sign-up integration
- **Password Security**: Minimum length requirements and secure hashing

### 2. Unified Workflow System
- **Intelligent Intent Detection**: AI agent automatically determines whether user wants:
  - Question answering (RAG) about document content with **topic suggestions**
  - Floor plan annotation/marking
- **Enhanced RAG with Suggestions**: When answering questions, the system now provides:
  - Comprehensive answer to the user's question
  - Related topic suggestions with page numbers
  - Topic descriptions to help users explore further
- **Single Endpoint**: `/agent/unified` handles both workflows seamlessly
- **Chat Interface**: Conversational interface with session management

### 3. Modular Design Benefits
- **Separation of Concerns**: Each module handles specific functionality
- **Maintainability**: Easy to update individual components
- **Testability**: Each module can be tested independently
- **Scalability**: Easy to add new features or modify existing ones

## New Capabilities

### Shared Project Workflows
- `GET /projects/shared` returns invitations and accepted shares for the authenticated user.
- `POST /projects/{project_id}/share/accept` and `/reject` let invitees control access while the backend tracks membership status.

### Subscription & Billing Platform
- Stripe-backed checkout limited to six-month and annual plans via `/billing/checkout`.
- `/billing/subscription` exposes the user’s current status so the frontend can gate premium features.
- Admin dashboard data is restored through `/admin/metrics/overview`, delivering totals and chart-ready timeseries.

### Durable Profile Avatars
- `/profile/avatar` stores uploads in S3 (or local fallback) with cache-busted URLs, preventing disappearing profile photos.

## Deployment & Operations

### 1. Run the subscription migration
```
python migrations/20240201_subscription_pricing.py
```

### 2. Create Stripe prices
Create one 6-month and one annual price in Stripe, then export their IDs to the API environment:
```
export STRIPE_API_KEY=sk_live_...
export STRIPE_WEBHOOK_SECRET=whsec_...
export STRIPE_PRICE_6M=price_...
export STRIPE_PRICE_12M=price_...
```

### 3. Configure profile storage
For S3-backed avatars set:
```
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
export AWS_DEFAULT_REGION=us-east-1
export AWS_S3_BUCKET=my-profile-bucket
export PROFILE_CDN_BASE_URL=https://cdn.example.com
```
The service falls back to local storage when the bucket or credentials are omitted.

### 4. Run tests
```
pytest
```
